from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import yaml

from bsbot.vision.detect import detect_template_multi


# Normalised ROI search bounds per detector (rx, ry, rw, rh).
ROI_SEARCH_BOUNDS: Dict[str, Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float]]] = {
    "nameplate": ((0.15, 0.65), (0.05, 0.45), (0.12, 0.45), (0.08, 0.28)),
    "attack": ((0.15, 0.70), (0.06, 0.55), (0.14, 0.46), (0.08, 0.32)),
}


STABLE_ENTER_STREAK = 6
STABLE_EXIT_FALLBACK = 2
FALLBACK_CAPTURE_MIN_STREAK = 2
RECENT_SUCCESS_WINDOW = 30.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class CalibrationResult:
    roi: Tuple[float, float, float, float]
    score: float


class CalibrationManager:
    """Handles automatic ROI calibration for template detectors."""

    def __init__(
        self,
        runtime,
        *,
        base_dir: str | Path | None = None,
        overrides_path: str | Path | None = None,
        capture_cooldown: float = 25.0,
    ) -> None:
        self.runtime = runtime
        self.base_dir = Path(base_dir or "logs/calibration")
        self.overrides_path = Path(overrides_path or "config/calibration/roi_overrides.yml")
        self.capture_cooldown = capture_cooldown
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="calibration")
        self._overrides: Dict[str, Optional[Tuple[float, float, float, float]]] = {
            "nameplate": None,
            "attack": None,
        }
        self._success_streak: Dict[str, int] = {"nameplate": 0, "attack": 0}
        self._fallback_streak: Dict[str, int] = {"nameplate": 0, "attack": 0}
        self._no_match_streak: Dict[str, int] = {"nameplate": 0, "attack": 0}
        self._last_capture_time: Dict[str, float] = {}
        self._last_capture_folder: Dict[str, Optional[str]] = {"nameplate": None, "attack": None}
        self._last_result: Dict[str, Optional[Dict[str, object]]] = {"nameplate": None, "attack": None}
        self._pending_jobs: Dict[str, int] = {"nameplate": 0, "attack": 0}
        self._last_success: Dict[str, Optional[Dict[str, object]]] = {"nameplate": None, "attack": None}
        self._last_capture_signature: Dict[str, Optional[Dict[str, object]]] = {"nameplate": None, "attack": None}
        self._stable_flags: Dict[str, bool] = {"nameplate": False, "attack": False}
        self._stable_since: Dict[str, float] = {"nameplate": 0.0, "attack": 0.0}

        self._load_overrides()
        self._update_status()

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)

    # ------------------------------------------------------------------
    def get_roi(self, key: str, default: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
        with self._lock:
            value = self._overrides.get(key) or default
        return value

    def template_success(
        self,
        key: str,
        score: float,
        roi: Optional[Tuple[float, float, float, float]] = None,
        box: Optional[Tuple[int, int, int, int]] = None,
    ) -> None:
        now = time.time()
        stable_event: Optional[Dict[str, float]] = None
        with self._lock:
            streak = self._success_streak.get(key, 0) + 1
            self._success_streak[key] = streak
            self._fallback_streak[key] = 0
            self._no_match_streak[key] = 0
            if roi is not None or box is not None:
                self._last_success[key] = {
                    "roi": list(roi) if roi else None,
                    "box": list(box) if box else None,
                    "score": float(score),
                    "ts": now,
                }
            was_stable = self._stable_flags.get(key, False)
            if streak >= STABLE_ENTER_STREAK:
                self._stable_flags[key] = True
                self._stable_since[key] = now
                if not was_stable:
                    stable_event = {"score": float(score), "streak": float(streak)}
            else:
                if was_stable:
                    self._stable_flags[key] = False
                    self._stable_since[key] = 0.0

        self.runtime.emit_event(
            "calibration",
            f"{key}_success",
            [0, 0, 0, 0],
            [],
            float(score),
            notes=f"template success score={score:.3f}",
        )
        if stable_event:
            self.runtime.emit_event(
                "calibration",
                f"CALIBRATING|{key}|STABLE",
                [0, 0, 0, 0],
                [],
                float(stable_event["score"]),
                notes=f"streak={int(stable_event['streak'])} score={stable_event['score']:.3f}",
            )
        self._update_status()

    def template_fallback(
        self,
        key: str,
        frame: np.ndarray,
        *,
        template_path: Optional[str],
        hint_box: Optional[Tuple[int, int, int, int]],
        confidence: float,
        state: str,
        phase: str,
        roi_rect: Sequence[int],
        boxes: Sequence[Tuple[int, int, int, int]] | None = None,
    ) -> None:
        if template_path is None:
            return
        now = time.time()

        centroid = None
        if hint_box:
            hx, hy, hw, hh = hint_box
            centroid = (hx + hw / 2.0, hy + hh / 2.0)

        skip_payload: Optional[Tuple[str, int]] = None
        stable_drop_event = False
        last_success_snapshot: Optional[Dict[str, object]] = None
        no_match_streak = 0
        overrides_present = False
        with self._lock:
            self._success_streak[key] = 0
            self._fallback_streak[key] = self._fallback_streak.get(key, 0) + 1
            fallback_streak = self._fallback_streak[key]
            pending_jobs = self._pending_jobs.get(key, 0)
            last_ts = self._last_capture_time.get(key, 0.0)
            last_sig = self._last_capture_signature.get(key)
            overrides_present = self._overrides.get(key) is not None
            last_success = self._last_success.get(key)
            last_success_ts = float(last_success.get("ts", 0.0)) if isinstance(last_success, dict) else 0.0
            was_stable = self._stable_flags.get(key, False)
            if was_stable and fallback_streak >= STABLE_EXIT_FALLBACK:
                self._stable_flags[key] = False
                self._stable_since[key] = 0.0
                stable_drop_event = True
            stable_active = self._stable_flags.get(key, False)

            reason = None
            should_capture = True

            if pending_jobs:
                reason = "job_in_progress"
                should_capture = False
            elif stable_active and fallback_streak < STABLE_EXIT_FALLBACK:
                reason = "stable_single_fallback"
                should_capture = False
            elif fallback_streak < FALLBACK_CAPTURE_MIN_STREAK:
                reason = "fallback_streak"
                should_capture = False
            elif now - last_ts < self.capture_cooldown and fallback_streak < 3:
                reason = "cooldown"
                should_capture = False
            elif last_success_ts and (now - last_success_ts) <= RECENT_SUCCESS_WINDOW:
                reason = "recent_success"
                should_capture = False
            elif centroid and last_sig and last_sig.get("centroid"):
                prev_cx, prev_cy = last_sig["centroid"]
                cx, cy = centroid
                if abs(prev_cx - cx) < 6.0 and abs(prev_cy - cy) < 6.0 and abs(float(last_sig.get("confidence", 0.0)) - confidence) < 0.05:
                    reason = "duplicate"
                    should_capture = False

            if not should_capture:
                skip_payload = (reason or "unknown", fallback_streak)
            else:
                self._last_capture_time[key] = now
                self._last_capture_folder[key] = None
                self._pending_jobs[key] += 1
                self._last_capture_signature[key] = {
                    "centroid": centroid,
                    "confidence": float(confidence),
                    "time": now,
                }
                last_success_snapshot = last_success.copy() if isinstance(last_success, dict) else None
                no_match_streak = self._no_match_streak.get(key, 0)

        if stable_drop_event:
            self.runtime.emit_event(
                "calibration",
                f"CALIBRATING|{key}|UNSTABLE",
                [0, 0, 0, 0],
                [],
                float(confidence),
                notes=f"streak={self._fallback_streak.get(key, 0)}",
                state=state,
                phase=phase,
            )

        if skip_payload is not None:
            reason, streak_value = skip_payload
            self.runtime.emit_event(
                "calibration",
                f"CALIBRATING|{key}|SKIP",
                [0, 0, 0, 0],
                [],
                float(confidence),
                notes=f"reason={reason} streak={streak_value}",
                state=state,
                phase=phase,
            )
            self._update_status()
            return

        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        folder = self.base_dir / f"{timestamp}_{key}"
        folder.mkdir(parents=True, exist_ok=True)
        image_path = folder / "frame.png"
        meta_path = folder / "fallback.json"
        cv2.imwrite(str(image_path), frame)

        meta = {
            "timestamp": timestamp,
            "detector": key,
            "confidence": float(confidence),
            "state": state,
            "phase": phase,
            "roi_rect": list(int(v) for v in roi_rect),
            "boxes": [list(map(int, box)) for box in boxes] if boxes else [],
            "hint_box": [int(v) for v in hint_box] if hint_box else None,
            "template_path": template_path,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        self.runtime.emit_event(
            "calibration",
            f"CALIBRATING|{key}|BEGIN",
            list(int(v) for v in roi_rect),
            [list(map(int, b)) for b in boxes] if boxes else [],
            float(confidence),
            notes=f"saved={folder.name} method=ocr",
            state=state,
            phase=phase,
        )

        with self._lock:
            self._last_capture_folder[key] = folder.name

        self._executor.submit(
            self._run_calibration,
            key,
            folder,
            image_path,
            template_path,
            hint_box,
            frame.shape[1],
            frame.shape[0],
            last_success_snapshot,
            no_match_streak,
            overrides_present,
        )
        self._update_status()

    # ------------------------------------------------------------------
    def to_status(self) -> Dict[str, object]:
        with self._lock:
            return {
                "overrides": {
                    k: list(v) if v else None
                    for k, v in self._overrides.items()
                },
                "success_streak": dict(self._success_streak),
                "fallback_streak": dict(self._fallback_streak),
                "no_match_streak": dict(self._no_match_streak),
                "last_capture": dict(self._last_capture_folder),
                "last_result": dict(self._last_result),
                "stable": dict(self._stable_flags),
                "stable_since": {
                    k: (
                        datetime.utcfromtimestamp(v).isoformat(timespec="seconds") + "Z"
                        if v
                        else None
                    )
                    for k, v in self._stable_since.items()
                },
                "last_success": {
                    k: v.copy() if isinstance(v, dict) else None
                    for k, v in self._last_success.items()
                },
                "pending_jobs": dict(self._pending_jobs),
                "capture_cooldown": self.capture_cooldown,
            }

    # ------------------------------------------------------------------
    def _run_calibration(
        self,
        key: str,
        folder: Path,
        image_path: Path,
        template_path: str,
        hint_box: Optional[Tuple[int, int, int, int]],
        frame_w: int,
        frame_h: int,
        last_success: Optional[Dict[str, object]],
        no_match_streak: int,
        has_override: bool,
    ) -> None:
        try:
            outcome = "NO_RESULT"
            frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            template = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if frame is None or template is None:
                raise RuntimeError("failed to load calibration assets")

            acceptance = self._current_acceptance_threshold(key, no_match_streak, has_override)
            result = self._sweep_roi(key, frame, template, hint_box, last_success, acceptance)
            data = {
                "detector": key,
                "score": None,
                "roi": None,
            }

            if result:
                data.update(
                    {
                        "score": result.score,
                        "roi": list(result.roi),
                    }
                )
                self._apply_override(key, result)
                self.runtime.emit_event(
                    "calibration",
                    f"CALIBRATING|{key}|APPLY",
                    [0, 0, 0, 0],
                    [],
                    float(result.score),
                    notes=f"roi={result.roi} score={result.score:.3f} saved={folder.name}",
                )
                outcome = f"APPLY score={result.score:.3f}"
            else:
                self.runtime.emit_event(
                    "calibration",
                    f"CALIBRATING|{key}|NO_MATCH",
                    [0, 0, 0, 0],
                    [],
                    0.0,
                    notes=f"no ROI >= threshold saved={folder.name}",
                )
                outcome = "NO_MATCH"

            (folder / "calibration.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            with self._lock:
                self._last_result[key] = data
                if result:
                    self._no_match_streak[key] = 0
                    self._fallback_streak[key] = 0
                else:
                    self._no_match_streak[key] = self._no_match_streak.get(key, 0) + 1
        except Exception as exc:  # pragma: no cover - defensive
            with self._lock:
                self._last_result[key] = {"error": str(exc)}
                self.runtime.logger.exception("calibration job failed | detector=%s", key)
                self.runtime.emit_event(
                "calibration",
                f"CALIBRATING|{key}|ERROR",
                [0, 0, 0, 0],
                [],
                0.0,
                notes=str(exc),
            )
            outcome = f"ERROR {exc}"
        finally:
            with self._lock:
                self._pending_jobs[key] = max(0, self._pending_jobs.get(key, 1) - 1)
            self._update_status()
            self.runtime.emit_event(
                "calibration",
                f"CALIBRATING|{key}|END",
                [0, 0, 0, 0],
                [],
                0.0,
                notes=outcome,
            )

    # ------------------------------------------------------------------
    def _sweep_roi(
        self,
        key: str,
        frame: np.ndarray,
        template: np.ndarray,
        hint_box: Optional[Tuple[int, int, int, int]],
        last_success: Optional[Dict[str, object]],
        acceptance: float,
    ) -> Optional[CalibrationResult]:
        bounds = ROI_SEARCH_BOUNDS.get(key, ((0.0, 1.0),) * 4)
        (rx_min, rx_max), (ry_min, ry_max), (rw_min, rw_max), (rh_min, rh_max) = bounds

        height, width = frame.shape[:2]
        tpl_h, tpl_w = template.shape[:2]

        # Focus search around hint when provided.
        if hint_box:
            hx, hy, hw, hh = hint_box
            cx = (hx + hw / 2) / width
            cy = (hy + hh / 2) / height
            rx_min = _clamp(cx - 0.25, 0.0, 1.0)
            rx_max = _clamp(cx + 0.25, 0.0, 1.0)
            ry_min = _clamp(cy - 0.25, 0.0, 1.0)
            ry_max = _clamp(cy + 0.25, 0.0, 1.0)
        elif last_success and last_success.get("roi"):
            lrx, lry, lrw, lrh = last_success["roi"]  # type: ignore[index]
            span = 0.08
            rx_min = _clamp(float(lrx) - span, 0.0, 1.0)
            rx_max = _clamp(float(lrx) + span, 0.0, 1.0)
            ry_min = _clamp(float(lry) - span, 0.0, 1.0)
            ry_max = _clamp(float(lry) + span, 0.0, 1.0)

        rx_values = np.linspace(rx_min, rx_max, 18)
        ry_values = np.linspace(ry_min, ry_max, 18)
        rw_min = max(rw_min, tpl_w / width + 0.02)
        rh_min = max(rh_min, tpl_h / height + 0.02)
        rw_values = np.linspace(rw_min, rw_max, 12)
        rh_values = np.linspace(rh_min, rh_max, 10)

        best_score = 0.0
        best_roi: Optional[Tuple[float, float, float, float]] = None

        for rx in rx_values:
            for ry in ry_values:
                for rw in rw_values:
                    for rh in rh_values:
                        x = int(round(rx * width))
                        y = int(round(ry * height))
                        w_px = int(round(rw * width))
                        h_px = int(round(rh * height))
                        if w_px <= 0 or h_px <= 0:
                            continue
                        if w_px < tpl_w or h_px < tpl_h:
                            continue
                        if x + w_px > width or y + h_px > height:
                            continue
                        roi = frame[y : y + h_px, x : x + w_px]
                        boxes, scores = detect_template_multi(roi, template, threshold=0.7)
                        if not scores:
                            continue
                        score = float(max(scores))
                        if score > best_score:
                            best_score = score
                            best_roi = (float(rx), float(ry), float(rw), float(rh))

        if best_roi and best_score >= acceptance:
            return CalibrationResult(best_roi, best_score)
        return None

    def _current_acceptance_threshold(self, key: str, no_match_streak: int, has_override: bool) -> float:
        base = 0.90 if has_override else 0.88
        drop = min(0.05, max(0, no_match_streak - 1) * 0.02)
        floor = 0.85 if has_override else 0.84
        return max(floor, base - drop)

    def _apply_override(self, key: str, result: CalibrationResult) -> None:
        with self._lock:
            self._overrides[key] = result.roi
        self._persist_overrides()

    # ------------------------------------------------------------------
    def _load_overrides(self) -> None:
        if not self.overrides_path.exists():
            return
        try:
            data = yaml.safe_load(self.overrides_path.read_text(encoding="utf-8")) or {}
            nameplate = data.get("nameplate_template_roi")
            attack = data.get("attack_template_roi")
            with self._lock:
                if isinstance(nameplate, (list, tuple)) and len(nameplate) == 4:
                    self._overrides["nameplate"] = tuple(float(v) for v in nameplate)
                if isinstance(attack, (list, tuple)) and len(attack) == 4:
                    self._overrides["attack"] = tuple(float(v) for v in attack)
        except Exception as exc:  # pragma: no cover - defensive
            self.runtime.logger.exception("Failed to load calibration overrides: %s", exc)

    def _persist_overrides(self) -> None:
        with self._lock:
            data = {
                "nameplate_template_roi": list(self._overrides.get("nameplate"))
                if self._overrides.get("nameplate")
                else None,
                "attack_template_roi": list(self._overrides.get("attack"))
                if self._overrides.get("attack")
                else None,
            }
        with self.overrides_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False)
        self._update_status()

    def _update_status(self) -> None:
        self.runtime.update_calibration_status(self.to_status())
