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
