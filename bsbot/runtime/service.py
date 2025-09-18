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
from bsbot.core.config import load_profile, load_monster_profile, load_interface_profile
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
    word: str = ""
    prefix_word: Optional[str] = None
    tesseract_path: Optional[str] = None
    method: str = "auto"  # auto, template, ocr
    click_mode: str = "dry_run"  # dry_run, live
    skill: str = "combat"
    monster_id: str = "twisted_wendigo"
    interface_id: str = "combat"
    phase: str = "Search for Monster"
    # Relative ROI (x,y,w,h) over the game client area.
    # Use full window by default to cover the whole app screen.
    roi: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    total_detections: int = 0


class DetectorRuntime:
    def __init__(self) -> None:
        self.logger = init_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
        self.status = DetectionStatus()
        profile = load_profile() or {}
        self.status.title = profile.get("window_title", self.status.title)
        default_template = profile.get("default_template_path")
        if default_template:
            self.status.template_path = default_template
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
        if not self.status.template_path:
            template_from_monster = monster_defaults.get("template")
            if template_from_monster:
                self.status.template_path = template_from_monster
        interface_defaults = load_interface_profile(self.status.interface_id) or {}
        if self.status.tesseract_path is None:
            self.status.tesseract_path = env_tesseract
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
            "prefix_word": self.status.prefix_word,
            "monster_id": self.status.monster_id,
            "interface_id": self.status.interface_id,
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
                if title: self.status.title = title
                if word is not None:
                    self.status.word = word
                if prefix_word is not None:
                    self.status.prefix_word = prefix_word or None
                if template_path is not None:
                    self.status.template_path = template_path or None
                if tesseract_path is not None:
                    self.status.tesseract_path = tesseract_path or None
                if method: self.status.method = method
                if roi: self.status.roi = roi
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
            if method: self.status.method = method
            if click_mode in {"dry_run", "live"}:
                self.status.click_mode = click_mode
            if template_path is not None:
                self.status.template_path = template_path or None
            if tesseract_path is not None:
                self.status.tesseract_path = tesseract_path or None
            if roi: self.status.roi = roi
            self.status.running = True
            self.status.paused = False
            self._stop_evt.clear()
            self._last_live_click.clear()
            self._recent_clicks.clear()
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
            time.sleep(self._loop_sleep)

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
    ) -> None:
        st = state or self._state
        ph = phase or self._phase
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
                    phase=ph,
                )
                self._record_recent_click(int(cx), int(cy), lbl)
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
