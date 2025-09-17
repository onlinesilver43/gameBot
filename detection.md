# Combat Detection Overview

Combat detection now lives inside a dedicated skill controller (`bsbot.skills.combat.controller.CombatController`) that drives the OCR-first pipeline, state machine, and planned clicks. The `DetectorRuntime` orchestrator spins the capture loop, delegates each frame to the active skill, and records timeline events while keeping reusable services (capture, logging, human-like clicking) in shared layers.

## bsbot/skills/combat/controller.py
```python
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from bsbot.skills.base import FrameContext, SkillController
from bsbot.vision.detect import (
    configure_tesseract,
    detect_digits_ocr_multi,
    detect_template_multi,
    detect_word_ocr_multi,
)


@dataclass
class PlannedClick:
    x: int
    y: int
    label: str

    def to_tuple(self) -> Tuple[int, int, str]:
        return self.x, self.y, self.label


class CombatController(SkillController):
    """State machine driving combat detection and interactions."""

    name = "combat"

    def __init__(self, runtime):
        super().__init__(runtime)
        self._state = "Scan"
        self._absent_counter = 0
        self._last_log_ts = 0.0
        self._last_found: Optional[bool] = None

    # ------------------------------------------------------------------
    def on_start(self, params: Dict[str, object] | None = None) -> None:
        self._state = "Scan"
        self._absent_counter = 0
        self._last_log_ts = 0.0
        self._last_found = None
        self.runtime.set_state(self._state)

    def on_stop(self) -> None:
        self._state = "Scan"
        self.runtime.set_state(self._state)

    def process_frame(self, frame, ctx: FrameContext) -> Tuple[Dict[str, object], Optional[bytes]]:
        status = self.runtime.status
        if status.method in {"auto", "ocr"}:
            configure_tesseract(status.tesseract_path)

        rx, ry = ctx.roi_origin
        rw, rh = ctx.roi_size
        roi_rect = [rx, ry, rw, rh]

        boxes: List[Tuple[int, int, int, int]] = []
        best_conf = 0.0
        method = status.method

        if method in {"auto", "template"} and status.template_path:
            tpl = cv2.imread(status.template_path, cv2.IMREAD_COLOR)
            if tpl is not None:
                tpl_boxes, scores = detect_template_multi(frame, tpl)
                boxes = tpl_boxes
                best_conf = max(scores) if scores else 0.0
                if method == "auto":
                    method = "template" if boxes else "ocr_fallback"
                else:
                    method = "template"

        if not boxes and method in {"auto", "ocr"}:
            boxes, best_conf = detect_word_ocr_multi(frame, target=status.word)
            if method == "auto":
                method = "ocr_fallback"
            else:
                method = "ocr"

        attack_boxes, attack_conf = detect_word_ocr_multi(frame, target=status.attack_word)

        # Focused HUD regions ------------------------------------------------
        apx, apy = int(0.55 * rw), int(0.20 * rh)
        apw, aph = int(0.40 * rw), int(0.60 * rh)
        ppx, ppy = int(0.55 * rw), int(0.07 * rh)
        ppw, pph = int(0.43 * rw), int(0.86 * rh)
        bbx, bby = int(0.10 * rw), int(0.83 * rh)
        bbw, bbh = int(0.80 * rw), int(0.15 * rh)

        attack_panel_roi = frame[apy:apy + aph, apx:apx + apw]
        prepare_panel_roi = frame[ppy:ppy + pph, ppx:ppx + ppw]
        bottom_bar_roi = frame[bby:bby + bbh, bbx:bbx + bbw]

        prep_boxes1, prep_conf1 = detect_word_ocr_multi(prepare_panel_roi, target="prepare")
        prep_boxes2, prep_conf2 = detect_word_ocr_multi(prepare_panel_roi, target="choose")
        prepare_boxes = [
            (ppx + bx, ppy + by, bw, bh)
            for (bx, by, bw, bh) in prep_boxes1 + prep_boxes2
        ]
        prepare_conf = max(prep_conf1, prep_conf2)

        spec_boxes_local, spec_conf = detect_word_ocr_multi(bottom_bar_roi, target="special")
        atks_boxes_local, atks_conf = detect_word_ocr_multi(bottom_bar_roi, target="attacks")
        spec_boxes = [(bbx + bx, bby + by, bw, bh) for (bx, by, bw, bh) in spec_boxes_local]
        atks_boxes = [(bbx + bx, bby + by, bw, bh) for (bx, by, bw, bh) in atks_boxes_local]
        special_attacks_present = bool(spec_boxes and atks_boxes)
        special_attacks_conf = min(spec_conf, atks_conf) if special_attacks_present else 0.0

        weapons_roi = self._subroi(prepare_panel_roi, (0.0, 0.50, 1.0, 0.50))
        digit_boxes_local, digit_conf = detect_digits_ocr_multi(weapons_roi, targets=("1",))
        wpx = ppx
        wpy = ppy + int(0.50 * pph)
        digit_boxes = [(wpx + bx, wpy + by, bw, bh) for (bx, by, bw, bh) in digit_boxes_local]

        planned_clicks: List[PlannedClick] = []
        if boxes:
            bx, by, bw, bh = boxes[0]
            cx = rx + bx + bw // 2
            cy = ry + by + int(1.4 * bh)
            planned_clicks.append(PlannedClick(cx, cy, "prime_nameplate"))
        if attack_boxes:
            bx, by, bw, bh = attack_boxes[0]
            cx = rx + bx + bw // 2
            cy = ry + by + bh // 2
            planned_clicks.append(PlannedClick(cx, cy, "attack_button"))
        if digit_boxes:
            bx, by, bw, bh = digit_boxes[0]
            cx = rx + bx + bw // 2
            cy = ry + by + bh // 2
            planned_clicks.append(PlannedClick(cx, cy, "weapon_1"))

        self._emit_detection_events(
            boxes,
            best_conf,
            attack_boxes,
            attack_conf,
            prepare_boxes,
            prepare_conf,
            special_attacks_present,
            special_attacks_conf,
            spec_boxes,
            atks_boxes,
            digit_boxes,
            digit_conf,
            roi_rect,
        )
        self._advance_state(boxes, attack_boxes, prepare_boxes, digit_boxes, special_attacks_present, planned_clicks, roi_rect)

        annotated = frame.copy()
        for (bx, by, bw, bh) in boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 0, 255), 2)
        for (bx, by, bw, bh) in attack_boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
        for (bx, by, bw, bh) in prepare_boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (255, 0, 0), 2)
        for (bx, by, bw, bh) in spec_boxes + atks_boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)
        for (bx, by, bw, bh) in digit_boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (255, 255, 0), 2)
        for planned in planned_clicks:
            fx = planned.x - rx
            fy = planned.y - ry
            cv2.drawMarker(annotated, (int(fx), int(fy)), (255, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=12, thickness=2)

        ok, jpg = cv2.imencode(".jpg", annotated)
        preview = jpg.tobytes() if ok else None

        count = len(boxes)
        if count:
            status.total_detections += count

        result = {
            "found": count > 0,
            "count": count,
            "confidence": best_conf,
            "method": method,
            "boxes": boxes,
            "attack": {
                "found": bool(attack_boxes),
                "count": len(attack_boxes),
                "confidence": attack_conf,
                "boxes": attack_boxes,
                "word": status.attack_word,
            },
            "prepare": {
                "found": bool(prepare_boxes),
                "count": len(prepare_boxes),
                "confidence": prepare_conf,
                "boxes": prepare_boxes,
            },
            "special_attacks": {
                "found": special_attacks_present,
                "confidence": special_attacks_conf,
                "special_boxes": spec_boxes,
                "attacks_boxes": atks_boxes,
            },
            "weapon_1": {
                "found": bool(digit_boxes),
                "count": len(digit_boxes),
                "confidence": digit_conf,
                "boxes": digit_boxes,
            },
            "planned_clicks": [
                {"x": planned.x, "y": planned.y, "label": planned.label}
                for planned in planned_clicks
            ],
            "total_detections": status.total_detections,
            "roi": roi_rect,
            "state": self._state,
        }

        self._log_detection(count > 0, count, best_conf, method, attack_boxes, attack_conf, prepare_boxes, prepare_conf, special_attacks_present, special_attacks_conf, digit_boxes, digit_conf)
        return result, preview

    # ------------------------------------------------------------------
    def _emit_detection_events(
        self,
        boxes,
        best_conf,
        attack_boxes,
        attack_conf,
        prepare_boxes,
        prepare_conf,
        special_attacks_present,
        special_attacks_conf,
        spec_boxes,
        atks_boxes,
        digit_boxes,
        digit_conf,
        roi_rect,
    ) -> None:
        if boxes:
            self.runtime.emit_event("detect", "nameplate", roi_rect, boxes, best_conf, state=self._state)
        if attack_boxes:
            self.runtime.emit_event("detect", "attack_button", roi_rect, attack_boxes, attack_conf, state=self._state)
        if prepare_boxes:
            self.runtime.emit_event("detect", "prepare_header", roi_rect, prepare_boxes, prepare_conf, state=self._state)
        if special_attacks_present:
            combined = spec_boxes + atks_boxes
            self.runtime.emit_event("confirm", "special_attacks", roi_rect, combined, special_attacks_conf, state=self._state)
        if digit_boxes:
            self.runtime.emit_event("detect", "weapon_slot_1", roi_rect, digit_boxes, digit_conf, state=self._state)

    def _advance_state(
        self,
        boxes,
        attack_boxes,
        prepare_boxes,
        digit_boxes,
        special_attacks_present,
        planned_clicks: List[PlannedClick],
        roi_rect,
    ) -> None:
        runtime = self.runtime
        click_tuples = [pc.to_tuple() for pc in planned_clicks]

        if self._state == "Scan":
            if boxes:
                runtime.emit_click(click_tuples, "prime_nameplate", state=self._state)
                self._transition("PrimeTarget")
        elif self._state == "PrimeTarget":
            if attack_boxes:
                runtime.emit_click(click_tuples, "attack_button", state=self._state)
                self._transition("AttackPanel")
            elif not boxes:
                self._transition("Scan")
        elif self._state == "AttackPanel":
            if prepare_boxes:
                self._transition("Prepare")
            elif not attack_boxes:
                self._transition("Scan")
        elif self._state == "Prepare":
            if digit_boxes:
                runtime.emit_click(click_tuples, "weapon_1", state=self._state)
                self._transition("Weapon")
            elif not prepare_boxes:
                self._transition("Scan")
        elif self._state == "Weapon":
            if special_attacks_present:
                self._transition("BattleLoop")
            elif not digit_boxes:
                self._transition("Scan")
        elif self._state == "BattleLoop":
            if special_attacks_present:
                self._absent_counter = 0
            else:
                self._absent_counter += 1
                if self._absent_counter >= 6:
                    runtime.emit_event("transition", "battle_end", roi_rect, [], 0.0, state=self._state, notes="absent M=6 frames")
                    self._transition("Scan")

    def _transition(self, new_state: str) -> None:
        prev = self._state
        self._state = new_state
        if new_state != "BattleLoop":
            self._absent_counter = 0
        self.runtime.set_state(new_state)
        self.runtime.emit_event("transition", f"{prev}->{new_state}", [0, 0, 0, 0], [], 0.0, state=new_state)

    def _log_detection(self, found: bool, count: int, best_conf: float, method: str, attack_boxes, attack_conf, prepare_boxes, prepare_conf, special_attacks_present: bool, special_attacks_conf: float, digit_boxes, digit_conf) -> None:
        now = time.time()
        if self._last_found is not found or now - self._last_log_ts > 2.0:
            self.runtime.logger.info("detect | found=%s count=%d conf=%.3f method=%s", found, count, best_conf, method)
            if attack_boxes:
                self.runtime.logger.info("detect_attack | found=True count=%d conf=%.3f", len(attack_boxes), attack_conf)
            if prepare_boxes:
                self.runtime.logger.info("detect_prepare | found=True count=%d conf=%.3f", len(prepare_boxes), prepare_conf)
            if special_attacks_present:
                self.runtime.logger.info("detect_special_attacks | found=True conf=%.3f", special_attacks_conf)
            if digit_boxes:
                self.runtime.logger.info("detect_weapon_1 | found=True count=%d conf=%.3f", len(digit_boxes), digit_conf)
            self._last_log_ts = now
            self._last_found = found

    @staticmethod
    def _subroi(img: np.ndarray, rel: Tuple[float, float, float, float]) -> np.ndarray:
        h, w = img.shape[:2]
        rx, ry, rw, rh = rel
        x = int(rx * w)
        y = int(ry * h)
        ww = int(rw * w)
        hh = int(rh * h)
        x = max(0, min(w - 1, x))
        y = max(0, min(h - 1, y))
        ww = max(1, min(w - x, ww))
        hh = max(1, min(h - y, hh))
        return img[y : y + hh, x : x + ww]

    # Utilities -----------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state
```

## bsbot/runtime/service.py
```python
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

import os

from bsbot.platform.win32 import window as win
from bsbot.platform import capture
from bsbot.core.logging import init_logging
from bsbot.skills.base import FrameContext, SkillController
from bsbot.skills.combat import CombatController


@dataclass
class DetectionStatus:
    running: bool = False
    paused: bool = False
    last_result: dict = field(default_factory=dict)
    last_frame: Optional[bytes] = None  # JPEG bytes for preview
    template_path: Optional[str] = None
    title: str = "Brighter Shores"
    word: str = "Wendigo"
    attack_word: str = "Attack"
    tesseract_path: Optional[str] = None
    method: str = "auto"  # auto, template, ocr
    click_mode: str = "dry_run"  # dry_run, live
    skill: str = "combat"
    # Relative ROI (x,y,w,h) over the game client area.
    # Use full window by default to cover the whole app screen.
    roi: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    total_detections: int = 0


class DetectorRuntime:
    def __init__(self) -> None:
        self.logger = init_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
        self.status = DetectionStatus()
        # pick up TESSERACT_PATH default if present
        self.status.tesseract_path = os.environ.get("TESSERACT_PATH") or None
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()
        # State/timeline
        self._state = "Scan"
        self._events: list[dict] = []
        # Skill management
        self._skills: Dict[str, SkillController] = {}
        self._skill_name: str = "combat"
        # Input helpers
        self._active_hwnd: Optional[int] = None
        self._last_live_click: dict[str, float] = {}
        self._click_cooldown = 0.45
        self._click_jitter_px = 5
        self._click_move_duration = 0.16
        self._click_down_delay = 0.05
        self._register_default_skills()

    def _register_default_skills(self) -> None:
        self._skills["combat"] = CombatController(self)

    def register_skill(self, name: str, controller: SkillController) -> None:
        self._skills[name] = controller

    def _set_skill(self, name: str) -> None:
        if name not in self._skills:
            raise ValueError(f"Unknown skill: {name}")
        self._skill_name = name
        self.status.skill = name

    def _get_controller(self) -> SkillController:
        return self._skills[self._skill_name]

    def _current_params(self) -> Dict[str, Any]:
        return {
            "title": self.status.title,
            "word": self.status.word,
            "attack_word": self.status.attack_word,
            "template_path": self.status.template_path,
            "tesseract_path": self.status.tesseract_path,
            "method": self.status.method,
            "roi": self.status.roi,
            "click_mode": self.status.click_mode,
        }

    def start(
        self,
        title: Optional[str] = None,
        word: Optional[str] = None,
        template_path: Optional[str] = None,
        tesseract_path: Optional[str] = None,
        method: Optional[str] = None,
        attack_word: Optional[str] = None,
        roi: Optional[Tuple[float, float, float, float]] = None,
        click_mode: Optional[str] = None,
        skill: Optional[str] = None,
    ) -> None:
        with self._lock:
            if skill:
                if self.status.running and skill != self._skill_name:
                    raise ValueError("Cannot change skill while runtime is active")
                self._set_skill(skill)
            if self.status.running:
                # Update parameters while running
                if title: self.status.title = title
                if word: self.status.word = word
                if attack_word: self.status.attack_word = attack_word
                if template_path: self.status.template_path = template_path
                if tesseract_path: self.status.tesseract_path = tesseract_path
                if method: self.status.method = method
                if roi: self.status.roi = roi
                if click_mode in {"dry_run", "live"}:
                    self.status.click_mode = click_mode
                self.status.paused = False
                self.logger.info("Runtime updated | title=%s word=%s template=%s method=%s", self.status.title, self.status.word, self.status.template_path, self.status.method)
                self._get_controller().on_update_params(self._current_params())
                return
            if title: self.status.title = title
            if word: self.status.word = word
            if attack_word: self.status.attack_word = attack_word
            if method: self.status.method = method
            if click_mode in {"dry_run", "live"}:
                self.status.click_mode = click_mode
            self.status.template_path = template_path
            self.status.tesseract_path = tesseract_path
            if roi: self.status.roi = roi
            self.status.running = True
            self.status.paused = False
            self._stop_evt.clear()
            self._last_live_click.clear()
            self._get_controller().on_start(self._current_params())
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self.logger.info("Runtime started | title=%s word=%s template=%s method=%s", self.status.title, self.status.word, self.status.template_path, self.status.method)

    def pause(self) -> None:
        with self._lock:
            if self.status.running:
                self.status.paused = True
                self.logger.info("Runtime paused")

    def stop(self) -> None:
        with self._lock:
            self._stop_evt.set()
            self.status.running = False
            self.status.paused = False
            try:
                self._get_controller().on_stop()
            except Exception:
                self.logger.exception("skill on_stop failed")
            self.logger.info("Runtime stopped")

    def _run_loop(self) -> None:
        win.make_dpi_aware()
        while not self._stop_evt.is_set():
            if self.status.paused:
                time.sleep(0.1)
                continue
            try:
                self._active_hwnd = None
                hwnd = win.find_window_exact(self.status.title)
                if not hwnd:
                    msg = {"error": f"Window not found: {self.status.title}"}
                    self._set_result(msg, frame=None)
                    time.sleep(0.5)
                    continue
                x, y, w, h = win.get_client_rect(hwnd)
                self._active_hwnd = hwnd
                rx, ry, rw, rh = self._roi_pixels(x, y, w, h)
                frame = capture.grab_rect(rx, ry, rw, rh)
                controller = self._get_controller()
                result, preview = controller.process_frame(
                    frame,
                    FrameContext(
                        hwnd=hwnd,
                        window_rect=(x, y, w, h),
                        roi_origin=(rx, ry),
                        roi_size=(rw, rh),
                    ),
                )
                self._set_result(result, preview)
            except Exception as e:
                self._set_result({"error": str(e)}, frame=None)
                self.logger.exception("runtime error")
            time.sleep(0.3)

    def _roi_pixels(self, x: int, y: int, w: int, h: int) -> Tuple[int, int, int, int]:
        rx, ry, rw, rh = self.status.roi
        return int(x + rx * w), int(y + ry * h), int(rw * w), int(rh * h)

    def _set_result(self, result: dict, frame: Optional[bytes]) -> None:
        with self._lock:
            self.status.last_result = result
            if frame is not None:
                self.status.last_frame = frame

    def snapshot(self) -> DetectionStatus:
        with self._lock:
            # Shallow copy is enough for read-only
            return self.status

    # Optional: expose recent event timeline (for future UI panel)
    def get_timeline(self) -> list[dict]:
        return list(self._events[-50:])

    # Event helpers
    def set_state(self, new_state: str) -> None:
        self._state = new_state

    def emit_click(self, planned: List[Tuple[int, int, str]], label: str, *, state: Optional[str] = None) -> None:
        st = state or self._state
        for entry in planned:
            if len(entry) != 3:
                continue
            cx, cy, lbl = entry
            if lbl == label:
                if self.status.click_mode == "live":
                    self._perform_live_click(int(cx), int(cy), label)
                self.emit_event(
                    "click",
                    lbl,
                    [0, 0, 0, 0],
                    [],
                    0.0,
                    click={"x": int(cx), "y": int(cy), "mode": self.status.click_mode},
                    state=st,
                )
                break

    def emit_event(
        self,
        etype: str,
        label: str,
        roi: List[int],
        boxes: List[Tuple[int, int, int, int]],
        best_conf: float,
        *,
        click: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        state: Optional[str] = None,
    ) -> None:
        st = state or self._state
        evt = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "state": st,
            "type": etype,
            "label": label,
            "roi": roi,
            "boxes": boxes,
            "best_conf": float(best_conf),
        }
        if click:
            evt["click"] = click
        if notes:
            evt["notes"] = notes
        with self._lock:
            self._events.append(evt)
            if len(self._events) > 200:
                self._events = self._events[-200:]
        # Also mirror to file log in a compact form
        self.logger.info("event | %s", evt)

    def _perform_live_click(self, x: int, y: int, label: str) -> None:
        now = time.time()
        last = self._last_live_click.get(label, 0.0)
        if now - last < self._click_cooldown:
            self.logger.debug("click cooldown active | label=%s", label)
            return
        self._last_live_click[label] = now
        try:
            from bsbot.platform.input import human_click

            human_click(
                (x, y),
                jitter_px=self._click_jitter_px,
                move_duration=self._click_move_duration,
                click_delay=self._click_down_delay,
                hwnd=self._active_hwnd,
            )
        except Exception as exc:
            self.logger.exception("live click failed | label=%s error=%s", label, exc)
```

## bsbot/vision/detect.py
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List
import os
import shutil

import cv2
import numpy as np
import pytesseract


@dataclass
class Detection:
    found: bool
    bbox: Optional[Tuple[int, int, int, int]] = None  # x, y, w, h in client coords
    confidence: float = 0.0
    method: str = ""


def _red_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lower1 = np.array([0, 120, 120], dtype=np.uint8)
    upper1 = np.array([10, 255, 255], dtype=np.uint8)
    lower2 = np.array([170, 120, 120], dtype=np.uint8)
    upper2 = np.array([180, 255, 255], dtype=np.uint8)
    m1 = cv2.inRange(hsv, lower1, upper1)
    m2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(m1, m2)
    mask = cv2.medianBlur(mask, 3)
    return mask


def configure_tesseract(explicit_path: Optional[str] = None) -> None:
    """Ensure pytesseract can find the tesseract.exe binary on Windows.

    Order of resolution:
    1) explicit_path if provided
    2) PATH lookup via shutil.which('tesseract')
    3) Common install locations under Program Files
    """
    cand: Optional[str] = None
    # 0) environment variable wins if present
    env_path = os.environ.get("TESSERACT_PATH")
    if not explicit_path and env_path:
        explicit_path = env_path

    if explicit_path and os.path.exists(explicit_path):
        cand = explicit_path
    else:
        found = shutil.which("tesseract")
        if found:
            cand = found
        else:
            defaults = [
                r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
                r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
            ]
            for p in defaults:
                if os.path.exists(p):
                    cand = p
                    break
    if cand:
        pytesseract.pytesseract.tesseract_cmd = cand


def detect_word_ocr(bgr: np.ndarray, target: str = "wendigo") -> Detection:
    """OCR-based single best match for ``target``.

    Tries a red-text focused pass first (for enemy nameplates),
    then falls back to a general grayscale OCR pass to support
    non-red UI elements like the "Attack" button.
    """
    # Ensure tesseract is configured; no-op if already set
    configure_tesseract()

    def _run_ocr(gray_like: np.ndarray, scale: float = 1.5) -> Detection:
        resized = cv2.resize(gray_like, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        cfg = "--psm 6 -l eng -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        try:
            data = pytesseract.image_to_data(resized, config=cfg, output_type=pytesseract.Output.DICT)
        except Exception:
            return Detection(False, method="ocr")
        best_det = Detection(False, method="ocr")
        n = len(data.get("text", []))
        for i in range(n):
            text = (data["text"][i] or "").strip().lower()
            if not text:
                continue
            conf_list = data.get("conf", [])
            conf_str = conf_list[i] if i < len(conf_list) else "0"
            try:
                conf_val = float(conf_str)
            except Exception:
                conf_val = 0.0
            if conf_val < 0:
                conf_val = 0.0
            lefts = data.get("left", []); tops = data.get("top", []);
            widths = data.get("width", []); heights = data.get("height", [])
            if i >= len(lefts) or i >= len(tops) or i >= len(widths) or i >= len(heights):
                continue
            x = int(lefts[i] / scale)
            y = int(tops[i] / scale)
            w = int(widths[i] / scale)
            h = int(heights[i] / scale)
            if text == target.lower():
                return Detection(True, (x, y, w, h), conf_val / 100.0, "ocr")
            if target.lower() in text:
                best_det = Detection(True, (x, y, w, h), conf_val / 100.0, "ocr_partial")
        return best_det

    # Pass 1: red mask (enemy nameplates like "Wendigo")
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    red_mask = _red_mask(bgr)
    masked = cv2.bitwise_and(gray, gray, mask=red_mask)
    det = _run_ocr(masked)
    if det.found:
        return det
    # Pass 2: general grayscale (white-on-dark UI like "Attack")
    return _run_ocr(gray)


def detect_word_ocr_multi(bgr: np.ndarray, target: str = "wendigo") -> Tuple[List[Tuple[int,int,int,int]], float]:
    """Return filtered boxes that match ``target`` via OCR with deduplication.

    Uses a two-pass strategy: red-mask first, then general grayscale fallback.
    This enables detecting both red enemy nameplates (e.g., "Wendigo") and
    white-on-dark UI text (e.g., "Attack").
    """
    def _collect_from(gray_like: np.ndarray, scale: float = 1.5) -> Tuple[List[Tuple[int,int,int,int]], List[float]]:
        cfg = "--psm 6 -l eng -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        resized = cv2.resize(gray_like, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        try:
            data = pytesseract.image_to_data(resized, config=cfg, output_type=pytesseract.Output.DICT)
        except Exception:
            return [], []
        boxes: List[Tuple[int,int,int,int]] = []
        scores: List[float] = []
        n = len(data.get("text", []))
        for i in range(n):
            text = (data["text"][i] or "").strip().lower()
            if not text:
                continue
            conf_list = data.get("conf", [])
            conf_str = conf_list[i] if i < len(conf_list) else "0"
            try:
                conf_val = float(conf_str)
            except Exception:
                conf_val = 0.0
            if conf_val < 0:
                conf_val = 0.0
            lefts = data.get("left", []); tops = data.get("top", []);
            widths = data.get("width", []); heights = data.get("height", [])
            if i >= len(lefts) or i >= len(tops) or i >= len(widths) or i >= len(heights):
                continue
            x = int(lefts[i] / scale)
            y = int(tops[i] / scale)
            w = int(widths[i] / scale)
            h = int(heights[i] / scale)
            if not _is_valid_text_box(w, h):
                continue
            if text == target.lower() or target.lower() in text:
                boxes.append((x, y, w, h))
                scores.append(conf_val / 100.0)
        return boxes, scores

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Pass 1: red mask
    red_mask = _red_mask(bgr)
    masked = cv2.bitwise_and(gray, gray, mask=red_mask)
    raw_boxes1, scores1 = _collect_from(masked)

    # If nothing found, pass 2: general grayscale (captures white text like "Attack")
    raw_boxes2, scores2 = ([], [])
    if not raw_boxes1:
        raw_boxes2, scores2 = _collect_from(gray)

    raw_boxes = raw_boxes1 + raw_boxes2
    scores = scores1 + scores2

    if raw_boxes and scores:
        keep_indices = _nms(raw_boxes, scores, iou_thresh=0.5)
        filtered_boxes = [raw_boxes[i] for i in keep_indices]
        filtered_scores = [scores[i] for i in keep_indices]
        best_conf = max(filtered_scores) if filtered_scores else 0.0
        return filtered_boxes, best_conf

    return [], 0.0


def _is_valid_text_box(width: int, height: int, min_size: int = 10, max_aspect: float = 8.0) -> bool:
    """Filter out noise boxes based on size and aspect ratio."""
    # Filter out boxes that are too small
    if width < min_size or height < min_size:
        return False

    # Filter out boxes with extreme aspect ratios (too wide or too tall)
    aspect_ratio = max(width, height) / min(width, height)
    if aspect_ratio > max_aspect:
        return False

    # Filter out boxes that are unreasonably large (likely false positives)
    max_dimension = 200  # pixels
    if width > max_dimension or height > max_dimension:
        return False

    return True


def _nms(boxes: List[Tuple[int,int,int,int]], scores: List[float], iou_thresh: float = 0.5) -> List[int]:
    if not boxes:
        return []
    # Convert to [x1,y1,x2,y2]
    x1 = np.array([b[0] for b in boxes], dtype=np.float32)
    y1 = np.array([b[1] for b in boxes], dtype=np.float32)
    x2 = np.array([b[0]+b[2] for b in boxes], dtype=np.float32)
    y2 = np.array([b[1]+b[3] for b in boxes], dtype=np.float32)
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = np.argsort(-np.array(scores))
    keep = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        inds = np.where(iou <= iou_thresh)[0]
        order = order[inds + 1]
    return keep


def detect_template_multi(bgr: np.ndarray, template_bgr: np.ndarray, threshold: float = 0.78, max_instances: int = 10) -> Tuple[List[Tuple[int,int,int,int]], List[float]]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    tpl_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    tpl_edges = cv2.Canny(tpl_gray, 80, 160)
    res = cv2.matchTemplate(edges, tpl_edges, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(res >= threshold)
    h, w = tpl_edges.shape[:2]
    boxes = [(int(x), int(y), int(w), int(h)) for y, x in zip(ys, xs)]
    scores = [float(res[y, x]) for y, x in zip(ys, xs)]
    # Apply NMS
    keep = _nms(boxes, scores, iou_thresh=0.5)
    boxes = [boxes[i] for i in keep][:max_instances]
    scores = [scores[i] for i in keep][:max_instances]
    return boxes, scores


def detect_digits_ocr_multi(bgr: np.ndarray, targets: List[str] | Tuple[str, ...] = ("1",)) -> Tuple[List[Tuple[int,int,int,int]], float]:
    """Detect one or more digit tokens via OCR within a region.

    - Restricts OCR to digits for better precision.
    - Returns deduplicated boxes and best confidence.
    """
    configure_tesseract()
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    scale = 1.5
    resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    cfg = "--psm 6 -l eng -c tessedit_char_whitelist=0123456789"
    try:
        data = pytesseract.image_to_data(resized, config=cfg, output_type=pytesseract.Output.DICT)
    except Exception:
        return [], 0.0

    targets_lc = {t.lower() for t in targets}
    raw_boxes: List[Tuple[int,int,int,int]] = []
    scores: List[float] = []
    n = len(data.get("text", []))
    for i in range(n):
        text = (data["text"][i] or "").strip().lower()
        if not text:
            continue
        if text not in targets_lc:
            continue
        conf_list = data.get("conf", [])
        conf_str = conf_list[i] if i < len(conf_list) else "0"
        try:
            conf_val = float(conf_str)
        except Exception:
            conf_val = 0.0
        if conf_val < 0:
            conf_val = 0.0
        lefts = data.get("left", []); tops = data.get("top", []);
        widths = data.get("width", []); heights = data.get("height", [])
        if i >= len(lefts) or i >= len(tops) or i >= len(widths) or i >= len(heights):
            continue
        x = int(lefts[i] / scale)
        y = int(tops[i] / scale)
        w = int(widths[i] / scale)
        h = int(heights[i] / scale)
        if not _is_valid_text_box(w, h):
            continue
        raw_boxes.append((x, y, w, h))
        scores.append(conf_val / 100.0)

    if raw_boxes and scores:
        keep_indices = _nms(raw_boxes, scores, iou_thresh=0.5)
        filtered_boxes = [raw_boxes[i] for i in keep_indices]
        filtered_scores = [scores[i] for i in keep_indices]
        best_conf = max(filtered_scores) if filtered_scores else 0.0
        return filtered_boxes, best_conf

    return [], 0.0


def detect_with_template(bgr: np.ndarray, template_bgr: np.ndarray, threshold: float = 0.78) -> Detection:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    tpl_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    tpl_edges = cv2.Canny(tpl_gray, 80, 160)
    res = cv2.matchTemplate(edges, tpl_edges, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    h, w = tpl_edges.shape[:2]
    if max_val >= threshold:
        x, y = max_loc
        return Detection(True, (x, y, w, h), float(max_val), "template")
    return Detection(False, None, float(max_val), "template")


def derive_hitbox_from_word(word_bbox: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    x, y, w, h = word_bbox
    cx = x + w // 2
    hy = int(y + h + 1.4 * h)
    hw = int(0.9 * w)
    hh = int(0.7 * h)
    return int(cx - hw // 2), int(hy - hh // 2), hw, hh
```

## config/elements/monsters.yml
```yaml
# Monster Detection Elements
# Template and color configurations for enemy detection

wendigo:
  template: "assets/templates/wendigo.png"
  regions:
    - [0.2, 0.25, 0.6, 0.5]  # Central ROI
  anchors:
    - { color: "0xFF0000", tolerance: 30 }  # Red health bars
  confidence_threshold: 0.65
  click_offset: [0, -20]

basic_enemy:
  regions:
    - [0.1, 0.1, 0.8, 0.6]
  anchors:
    - { color: "0xFF0000", tolerance: 30 }
  confidence_threshold: 0.6

boss_enemy:
  regions:
    - [0.05, 0.05, 0.9, 0.7]
  anchors:
    - { color: "0xFFD700", tolerance: 40 }  # Gold/yellow
  confidence_threshold: 0.7
  click_offset: [0, -30]
```
