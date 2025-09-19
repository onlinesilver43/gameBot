from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

import os
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler

from bsbot.platform.win32 import window as win
from bsbot.platform import capture
from bsbot.core.logging import init_logging
from bsbot.core.config import (
    load_profile,
    load_monster_profile,
    load_interface_profile,
    list_interactable_profiles,
    save_interactable_coords,
)
from bsbot.skills.base import FrameContext, SkillController
from bsbot.skills.combat import CombatController
from bsbot.skills.carpenter import CarpenterController
from bsbot.navigation import (
    CompassCalibrator,
    CompassManager,
    CompassSettings,
    MinimapManager,
    MinimapSettings,
)
from bsbot.calibration import CalibrationManager


@dataclass
class DetectionStatus:
    running: bool = False
    paused: bool = False
    last_result: dict = field(default_factory=dict)
    last_frame: Optional[bytes] = None  # JPEG bytes for preview
    template_path: Optional[str] = None
    template_source: Optional[str] = None
    title: str = "Brighter Shores"
    word: str = ""
    prefix_word: Optional[str] = None
    tesseract_path: Optional[str] = None
    method: str = "auto"  # auto, template, ocr
    click_mode: str = "dry_run"  # dry_run, live
    skill: str = "combat"
    monster_id: str = "twisted_wendigo"
    interface_id: str = "combat"
    phase: str = "Search for Monster"
    tile_size_px: Optional[float] = None
    tile_origin_px: Tuple[float, float] = (0.0, 0.0)
    player_tile_offset: Tuple[float, float] = (0.5, 0.5)
    compass_auto_align: bool = False
    compass_roi: Tuple[float, float, float, float] = (0.88, 0.04, 0.08, 0.12)
    compass_align_threshold_deg: float = 5.0
    compass_drift_threshold_deg: float = 8.0
    compass_sample_interval_s: float = 2.5
    compass_rotate_keys: Tuple[str, str] = ("left", "right")
    compass_rotation_rate_deg_s: float = 120.0
    compass_rotation_hold_s: float = 0.16
    compass_angle_deg: Optional[float] = None
    compass_last_aligned: Optional[float] = None
    minimap_toggle_key: str = "m"
    minimap_roi: Tuple[float, float, float, float] = (0.74, 0.1, 0.22, 0.32)
    minimap_coords_roi: Tuple[float, float, float, float] = (0.79, 0.4, 0.16, 0.1)
    minimap_anchor_interval_s: float = 45.0
    minimap_last_anchor: Optional[float] = None
    world_tile: Optional[Tuple[int, int]] = None
    minimap_auto_anchor: bool = False
    interactables: List[Dict[str, Any]] = field(default_factory=list)
    # Relative ROI (x,y,w,h) over the game client area.
    # Use full window by default to cover the whole app screen.
    roi: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    total_detections: int = 0
    roi_px: Optional[Tuple[int, int, int, int]] = None
    roi_reference_size: Optional[Tuple[int, int]] = None
    calibration: Dict[str, Any] = field(default_factory=dict)


class DetectorRuntime:
    def __init__(self) -> None:
        self.logger = init_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
        self.status = DetectionStatus()
        profile = load_profile() or {}
        self.status.title = profile.get("window_title", self.status.title)
        self._template_default_path: Optional[str] = profile.get("default_template_path") or None
        self._template_override_path: Optional[str] = None
        self.status.template_path = self._template_default_path
        tess_from_profile = profile.get("tesseract_path")
        # pick up TESSERACT_PATH environment fallback
        env_tesseract = os.environ.get("TESSERACT_PATH")
        self.status.tesseract_path = tess_from_profile or env_tesseract or self.status.tesseract_path
        self.status.monster_id = profile.get("default_monster", self.status.monster_id)
        self.status.interface_id = profile.get("default_interface", self.status.interface_id)
        monster_defaults = load_monster_profile(self.status.monster_id) or {}
        if monster_defaults.get("word"):
            self.status.word = monster_defaults["word"]
        self.status.prefix_word = monster_defaults.get("prefix")
        interface_defaults = load_interface_profile(self.status.interface_id) or {}
        if self.status.tesseract_path is None:
            self.status.tesseract_path = env_tesseract
        tile_size = profile.get("tile_size_px")
        if tile_size:
            try:
                self.status.tile_size_px = float(tile_size)
            except (TypeError, ValueError):
                self.status.tile_size_px = None
        origin = profile.get("tile_origin_px") or [0, 0]
        if isinstance(origin, (list, tuple)) and len(origin) == 2:
            self.status.tile_origin_px = (float(origin[0]), float(origin[1]))
        player_off = profile.get("player_tile_offset") or [0.5, 0.5]
        if isinstance(player_off, (list, tuple)) and len(player_off) == 2:
            self.status.player_tile_offset = (float(player_off[0]), float(player_off[1]))
        compass_auto = profile.get("compass_auto_align")
        if isinstance(compass_auto, bool):
            self.status.compass_auto_align = compass_auto
        compass_cfg = profile.get("compass", {})
        if isinstance(compass_cfg, dict):
            roi = compass_cfg.get("roi")
            if isinstance(roi, (list, tuple)) and len(roi) == 4:
                self.status.compass_roi = tuple(float(v) for v in roi)  # type: ignore[arg-type]
            self.status.compass_align_threshold_deg = float(compass_cfg.get("align_threshold_deg", self.status.compass_align_threshold_deg))
            self.status.compass_drift_threshold_deg = float(compass_cfg.get("drift_threshold_deg", self.status.compass_drift_threshold_deg))
            self.status.compass_sample_interval_s = float(compass_cfg.get("sample_interval_s", self.status.compass_sample_interval_s))
            rotate_keys = compass_cfg.get("rotate_keys")
            if isinstance(rotate_keys, (list, tuple)) and len(rotate_keys) == 2:
                self.status.compass_rotate_keys = (str(rotate_keys[0]), str(rotate_keys[1]))
            self.status.compass_rotation_rate_deg_s = float(compass_cfg.get("rotation_rate_deg_s", self.status.compass_rotation_rate_deg_s))
            self.status.compass_rotation_hold_s = float(compass_cfg.get("rotation_hold_s", self.status.compass_rotation_hold_s))
        minimap_cfg = profile.get("minimap", {})
        if isinstance(minimap_cfg, dict):
            roi = minimap_cfg.get("roi")
            if isinstance(roi, (list, tuple)) and len(roi) == 4:
                self.status.minimap_roi = tuple(float(v) for v in roi)  # type: ignore[arg-type]
            coords_roi = minimap_cfg.get("coords_roi")
            if isinstance(coords_roi, (list, tuple)) and len(coords_roi) == 4:
                self.status.minimap_coords_roi = tuple(float(v) for v in coords_roi)  # type: ignore[arg-type]
            toggle = minimap_cfg.get("toggle_key")
            if isinstance(toggle, str) and toggle:
                self.status.minimap_toggle_key = toggle
            anchor_interval = minimap_cfg.get("anchor_interval_s")
            if anchor_interval is not None:
                try:
                    self.status.minimap_anchor_interval_s = float(anchor_interval)
                except (TypeError, ValueError):
                    pass
        self.status.phase = "Search for Monster"
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()
        # State/timeline
        self._state = "Scan"
        self._phase = self.status.phase
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
        self._recent_clicks: List[Dict[str, Any]] = []
        default_loop_sleep = 0.1
        try:
            env_loop = os.environ.get("BSBOT_LOOP_SLEEP")
            self._loop_sleep = float(env_loop) if env_loop else default_loop_sleep
        except (TypeError, ValueError):
            self._loop_sleep = default_loop_sleep
        self._register_default_skills()
        compass_settings = CompassSettings(
            roi=self.status.compass_roi,
            align_threshold_deg=self.status.compass_align_threshold_deg,
            drift_threshold_deg=self.status.compass_drift_threshold_deg,
            sample_interval_s=self.status.compass_sample_interval_s,
            rotate_keys=self.status.compass_rotate_keys,
            rotation_rate_deg_s=self.status.compass_rotation_rate_deg_s,
            rotation_hold_s=self.status.compass_rotation_hold_s,
        )
        self._compass_manager: Optional[CompassManager] = None
        if self.status.compass_auto_align:
            self._compass_manager = CompassManager(self, settings=compass_settings, calibrator=CompassCalibrator())
        minimap_settings = MinimapSettings(
            toggle_key=self.status.minimap_toggle_key,
            roi=self.status.minimap_roi,
            coords_roi=self.status.minimap_coords_roi,
            anchor_interval_s=self.status.minimap_anchor_interval_s,
        )
        self._minimap_manager = MinimapManager(self, settings=minimap_settings)
        self.status.interactables = list_interactable_profiles()
        self._interactable_records: Dict[str, List[Dict[str, Any]]] = {}
        self._records_path = Path(os.environ.get("BSBOT_INTERACTABLE_RECORDS", "logs/interactable_positions.json"))
        self._load_interactable_records()
        self._roi_config = {"pixels": None, "reference": None}
        self._configure_initial_roi(profile)
        self.calibration = CalibrationManager(
            self,
            base_dir=os.environ.get("BSBOT_CALIBRATION_DIR", "logs/calibration"),
            overrides_path=os.environ.get("BSBOT_CALIBRATION_OVERRIDES", "config/calibration/roi_overrides.yml"),
        )
        self.update_calibration_status(self.calibration.to_status())

    def _register_default_skills(self) -> None:
        self._skills["combat"] = CombatController(self)
        self._skills["carpenter"] = CarpenterController(self)

    def register_skill(self, name: str, controller: SkillController) -> None:
        self._skills[name] = controller

    def _configure_initial_roi(self, profile: Dict[str, Any]) -> None:
        normalized: Optional[Tuple[float, float, float, float]] = None
        pixels: Optional[Tuple[int, int, int, int]] = None
        reference: Optional[Tuple[int, int]] = None

        # Legacy normalized keys
        legacy_keys = ["roi_x", "roi_y", "roi_width", "roi_height"]
        if all(k in profile for k in legacy_keys):
            try:
                normalized = (
                    float(profile["roi_x"]),
                    float(profile["roi_y"]),
                    float(profile["roi_width"]),
                    float(profile["roi_height"]),
                )
            except (TypeError, ValueError):
                normalized = None

        # Support compact list under profile["roi"] if present
        if normalized is None:
            roi_list = profile.get("roi")
            if isinstance(roi_list, (list, tuple)) and len(roi_list) == 4:
                try:
                    normalized = tuple(float(v) for v in roi_list)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    normalized = None

        # Pixel-based ROI block
        roi_pixels_cfg = profile.get("roi_pixels") or profile.get("roi_px")
        if isinstance(roi_pixels_cfg, dict):
            try:
                px = int(roi_pixels_cfg.get("x"))
                py = int(roi_pixels_cfg.get("y"))
                pw = int(roi_pixels_cfg.get("width"))
                ph = int(roi_pixels_cfg.get("height"))
                pixels = (px, py, pw, ph)
                if "reference_size" in roi_pixels_cfg:
                    ref = roi_pixels_cfg["reference_size"]
                    if isinstance(ref, (list, tuple)) and len(ref) == 2:
                        reference = (int(ref[0]), int(ref[1]))
                else:
                    ref_w = roi_pixels_cfg.get("reference_width")
                    ref_h = roi_pixels_cfg.get("reference_height")
                    if ref_w is not None and ref_h is not None:
                        reference = (int(ref_w), int(ref_h))
            except (TypeError, ValueError):
                pixels = None
                reference = None

        # If pixels and reference are available, derive normalized fallback
        if pixels and reference and reference[0] > 0 and reference[1] > 0:
            px, py, pw, ph = pixels
            ref_w, ref_h = reference
            normalized = (
                max(0.0, min(1.0, px / ref_w)),
                max(0.0, min(1.0, py / ref_h)),
                max(0.0, min(1.0, pw / ref_w)),
                max(0.0, min(1.0, ph / ref_h)),
            )
        if normalized is None:
            normalized = (0.0, 0.0, 1.0, 1.0)

        self._apply_roi_config(normalized, pixels if reference else None, reference)

    def _apply_roi_config(
        self,
        normalized: Tuple[float, float, float, float],
        pixels: Optional[Tuple[int, int, int, int]] = None,
        reference: Optional[Tuple[int, int]] = None,
    ) -> None:
        self.status.roi = tuple(max(0.0, min(1.0, float(v))) for v in normalized)
        self.status.roi_px = pixels
        self.status.roi_reference_size = reference
        self._roi_config = {"pixels": pixels, "reference": reference}

    def _roll_run_log(self) -> None:
        handlers = getattr(self.logger, "handlers", [])
        for handler in handlers:
            if isinstance(handler, RotatingFileHandler):
                try:
                    handler.doRollover()
                except Exception:
                    self.logger.exception("Failed to rollover log handler")

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
            "prefix_word": self.status.prefix_word,
            "monster_id": self.status.monster_id,
            "interface_id": self.status.interface_id,
            "template_path": self._template_override_path,
            "template_override": self._template_override_path,
            "template_default": self._template_default_path,
            "tesseract_path": self.status.tesseract_path,
            "method": self.status.method,
            "roi": self.status.roi,
            "click_mode": self.status.click_mode,
            "tile_size_px": self.status.tile_size_px,
            "tile_origin_px": self.status.tile_origin_px,
            "player_tile_offset": self.status.player_tile_offset,
            "world_tile": self.status.world_tile,
        }

    def start(
        self,
        title: Optional[str] = None,
        word: Optional[str] = None,
        prefix_word: Optional[str] = None,
        template_path: Optional[str] = None,
        tesseract_path: Optional[str] = None,
        method: Optional[str] = None,
        roi: Optional[Tuple[float, float, float, float]] = None,
        click_mode: Optional[str] = None,
        skill: Optional[str] = None,
        monster_id: Optional[str] = None,
        interface_id: Optional[str] = None,
    ) -> None:
        with self._lock:
            if skill:
                if self.status.running and skill != self._skill_name:
                    raise ValueError("Cannot change skill while runtime is active")
                self._set_skill(skill)
            if monster_id:
                if self.status.running and monster_id != self.status.monster_id:
                    raise ValueError("Cannot change monster while runtime is active")
                self.status.monster_id = monster_id
            if interface_id:
                if self.status.running and interface_id != self.status.interface_id:
                    raise ValueError("Cannot change interface while runtime is active")
                self.status.interface_id = interface_id
            if self.status.running:
                # Update parameters while running
                if title:
                    self.status.title = title
                if word is not None:
                    self.status.word = word
                if prefix_word is not None:
                    self.status.prefix_word = prefix_word or None
                if template_path is not None:
                    self._template_override_path = template_path or None
                    if self._template_override_path:
                        self.status.template_path = self._template_override_path
                        self.status.template_source = "override"
                if tesseract_path is not None:
                    self.status.tesseract_path = tesseract_path or None
                if method:
                    self.status.method = method
                if roi:
                    self._apply_roi_config(roi, None, None)
                if click_mode in {"dry_run", "live"}:
                    self.status.click_mode = click_mode
                self.status.paused = False
                self.logger.info(
                    "Runtime updated | title=%s monster=%s interface=%s method=%s click_mode=%s",
                    self.status.title,
                    self.status.monster_id,
                    self.status.interface_id,
                    self.status.method,
                    self.status.click_mode,
                )
                self._get_controller().on_update_params(self._current_params())
                return
            if title: self.status.title = title
            if word is not None:
                self.status.word = word
            if prefix_word is not None:
                self.status.prefix_word = prefix_word or None
            if monster_id:
                self.status.monster_id = monster_id
            if interface_id:
                self.status.interface_id = interface_id
            if method:
                self.status.method = method
            if click_mode in {"dry_run", "live"}:
                self.status.click_mode = click_mode
            if template_path is not None:
                self._template_override_path = template_path or None
            if tesseract_path is not None:
                self.status.tesseract_path = tesseract_path or None
            if roi:
                self._apply_roi_config(roi, None, None)
            else:
                self._apply_roi_config(self.status.roi, self._roi_config.get("pixels"), self._roi_config.get("reference"))
            if self._template_override_path:
                self.status.template_path = self._template_override_path
                self.status.template_source = "override"
            else:
                self.status.template_path = self._template_default_path
                self.status.template_source = "default" if self._template_default_path else None
            self.status.running = True
            self.status.paused = False
            self._stop_evt.clear()
            self._last_live_click.clear()
            self._recent_clicks.clear()
            self._roll_run_log()
            self._get_controller().on_start(self._current_params())
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self.logger.info(
                "Runtime started | title=%s monster=%s interface=%s method=%s click_mode=%s",
                self.status.title,
                self.status.monster_id,
                self.status.interface_id,
                self.status.method,
                self.status.click_mode,
            )

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
        if hasattr(self, "calibration"):
            self.calibration.shutdown()

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
                if self.status.compass_auto_align and self._compass_manager:
                    self._compass_manager.ensure_aligned((x, y, w, h))
                if self._minimap_manager and self.status.minimap_auto_anchor:
                    self._minimap_manager.maybe_anchor((x, y, w, h))
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
            time.sleep(self._loop_sleep)

    def _roi_pixels(self, x: int, y: int, w: int, h: int) -> Tuple[int, int, int, int]:
        config_pixels = self._roi_config.get("pixels") if hasattr(self, "_roi_config") else None
        reference = self._roi_config.get("reference") if hasattr(self, "_roi_config") else None

        if config_pixels and reference and reference[0] > 0 and reference[1] > 0:
            px, py, pw, ph = config_pixels
            ref_w, ref_h = reference
            scale_x = w / ref_w
            scale_y = h / ref_h
            rx_px = int(round(px * scale_x))
            ry_px = int(round(py * scale_y))
            rw_px = int(round(pw * scale_x))
            rh_px = int(round(ph * scale_y))

            rx_px = max(0, min(w - 1, rx_px))
            ry_px = max(0, min(h - 1, ry_px))
            rw_px = max(1, min(w - rx_px, rw_px))
            rh_px = max(1, min(h - ry_px, rh_px))

            normalized = (
                rx_px / w if w else 0.0,
                ry_px / h if h else 0.0,
                rw_px / w if w else 1.0,
                rh_px / h if h else 1.0,
            )
            self.status.roi = normalized
            self.status.roi_px = (rx_px, ry_px, rw_px, rh_px)
            return x + rx_px, y + ry_px, rw_px, rh_px

        rx, ry, rw, rh = self.status.roi
        rel_x = int(round(rx * w))
        rel_y = int(round(ry * h))
        width_px = int(round(rw * w))
        height_px = int(round(rh * h))
        rel_x = max(0, min(w - 1, rel_x))
        rel_y = max(0, min(h - 1, rel_y))
        width_px = max(1, min(w - rel_x, width_px))
        height_px = max(1, min(h - rel_y, height_px))
        abs_x = x + rel_x
        abs_y = y + rel_y
        self.status.roi_px = (rel_x, rel_y, width_px, height_px)
        return abs_x, abs_y, width_px, height_px

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

    def set_phase(self, phase: str) -> None:
        self._phase = phase
        self.status.phase = phase

    def emit_click(
        self,
        planned: List[Tuple[int, int, str]],
        label: str,
        *,
        state: Optional[str] = None,
        phase: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        st = state or self._state
        ph = phase or self._phase
        for entry in planned:
            if len(entry) < 3:
                continue
            cx, cy, lbl = entry[:3]
            action = entry[3] if len(entry) > 3 else "click"
            if lbl == label:
                event_type = "click"
                if action == "hover":
                    self._perform_hover(int(cx), int(cy), label)
                    event_type = "hover"
                else:
                    if self.status.click_mode == "live":
                        self._perform_live_click(int(cx), int(cy), label)
                    self._record_recent_click(int(cx), int(cy), lbl)
                self.emit_event(
                    event_type,
                    lbl,
                    [0, 0, 0, 0],
                    [],
                    0.0,
                    click={"x": int(cx), "y": int(cy), "mode": self.status.click_mode, "action": action},
                    state=st,
                    phase=ph,
                    notes=notes,
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
        phase: Optional[str] = None,
    ) -> None:
        st = state or self._state
        ph = phase or self._phase
        evt = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "state": st,
            "phase": ph,
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

    def _perform_hover(self, x: int, y: int, label: str) -> None:
        try:
            from bsbot.platform.input import human_move

            human_move(
                (x, y),
                jitter_px=self._click_jitter_px,
                move_duration=self._click_move_duration,
                hwnd=self._active_hwnd,
            )
        except Exception as exc:
            self.logger.exception("hover failed | label=%s error=%s", label, exc)

    def _record_recent_click(self, x: int, y: int, label: str) -> None:
        now = time.time()
        with self._lock:
            self._recent_clicks.append({"ts": now, "x": x, "y": y, "label": label})
            # keep last 10 clicks
            if len(self._recent_clicks) > 10:
                self._recent_clicks = self._recent_clicks[-10:]

    def get_recent_clicks(self, max_age: float = 1.0) -> List[Dict[str, Any]]:
        cutoff = time.time() - max_age
        with self._lock:
            fresh = [c for c in self._recent_clicks if c["ts"] >= cutoff]
            if len(fresh) != len(self._recent_clicks):
                self._recent_clicks = fresh
            return [c.copy() for c in fresh]

    def update_compass_status(self, *, angle: Optional[float] = None, aligned: bool = False) -> None:
        now = time.time()
        with self._lock:
            if angle is not None:
                self.status.compass_angle_deg = float(angle)
            if aligned:
                self.status.compass_last_aligned = now

    def update_minimap_anchor(self, anchor) -> None:
        from bsbot.navigation.minimap import MinimapAnchor

        if not isinstance(anchor, MinimapAnchor):
            return
        now = time.time()
        with self._lock:
            self.status.world_tile = anchor.world_tile
            self.status.minimap_last_anchor = now

    def update_calibration_status(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self.status.calibration = data

    # Interactable recordings -------------------------------------------------
    def _load_interactable_records(self) -> None:
        path = self._records_path
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    self._interactable_records = {
                        str(k): list(v) if isinstance(v, list) else []
                        for k, v in data.items()
                    }
        except Exception:
            self.logger.exception("Failed to load interactable records")
            self._interactable_records = {}

    def _persist_interactable_records(self) -> None:
        path = self._records_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as fh:
                json.dump(self._interactable_records, fh, indent=2)
        except Exception:
            self.logger.exception("Failed to persist interactable records")

    def list_interactable_records(self) -> Dict[str, List[Dict[str, Any]]]:
        with self._lock:
            return json.loads(json.dumps(self._interactable_records))

    def record_interactable_position(
        self,
        interactable_id: str,
        *,
        roi_rel: Tuple[float, float],
        screen_xy: Tuple[int, int],
        roi_xy: Tuple[int, int],
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        entry = {
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "roi_rel": [float(roi_rel[0]), float(roi_rel[1])],
            "roi_xy": [int(roi_xy[0]), int(roi_xy[1])],
            "screen_xy": [int(screen_xy[0]), int(screen_xy[1])],
        }
        if notes:
            entry["notes"] = notes
        with self._lock:
            bucket = self._interactable_records.setdefault(interactable_id, [])
            bucket.append(entry)
            self._persist_interactable_records()
        return entry

    def save_interactable_profile(
        self,
        interactable_id: str,
        *,
        coords: Tuple[float, float],
        roi_xy: Optional[Tuple[int, int]] = None,
        screen_xy: Optional[Tuple[int, int]] = None,
        element_index: int = 0,
    ) -> Dict[str, Any]:
        profile = save_interactable_coords(
            interactable_id,
            coords=coords,
            roi_xy=roi_xy,
            screen_xy=screen_xy,
            element_index=element_index,
        )
        # refresh list so UI picks up new metadata
        with self._lock:
            self.status.interactables = list_interactable_profiles()
        return profile
