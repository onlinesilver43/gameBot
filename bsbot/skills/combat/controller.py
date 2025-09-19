from __future__ import annotations

import time
from collections import deque
from difflib import SequenceMatcher
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract

from bsbot.skills.base import FrameContext, SkillController
from bsbot.core.config import load_monster_profile, load_interface_profile
from bsbot.tracking import TileGrid, TileTracker
from bsbot.vision.detect import (
    configure_tesseract,
    detect_digits_ocr_multi,
    detect_template_multi,
    detect_word_ocr_multi,
    derive_hitbox_from_word,
)


@dataclass
class PlannedClick:
    x: int
    y: int
    label: str
    action: str = "click"
    source: str = ""

    def to_tuple(self) -> Tuple[int, int, str, str]:
        return self.x, self.y, self.label, self.action


@dataclass
class HoverState:
    tile: Optional[Tuple[int, int]] = None
    active: bool = False
    confirmed: bool = False
    last_hover_ts: float = 0.0
    last_detect_ts: float = 0.0
    attempts: int = 0

    def reset(self) -> None:
        self.tile = None
        self.active = False
        self.confirmed = False
        self.last_hover_ts = 0.0
        self.last_detect_ts = 0.0
        self.attempts = 0


PHASE_STATE_DEFAULTS: Dict[str, str] = {
    "Scan": "Search for Monster",
    "PrimeTarget": "Click on the Monster",
    "AttackPanel": "Detect the Attack Box",
    "Prepare": "Detect the “Prepare for Battle” box",
    "Weapon": "Detect the Weapon box inside that panel",
    "BattleLoop": "Detect the fight has started",
}

PHASE_DETECT_EVENTS: Dict[str, str] = {
    "nameplate": "Detect Monster Nameplate",
    "name_prefix": "Detect Monster Nameplate",
    "attack_button": "Detect the Attack Box",
    "prepare_header": "Detect the “Prepare for Battle” box",
    "weapon_slot_1": "Detect the Weapon box inside that panel",
}

PHASE_CLICK_EVENTS: Dict[str, str] = {
    "prime_nameplate": "Click on the Monster",
    "attack_button": "Click the Attack Box",
    "weapon_1": "Click the Weapon box (defaulting to slot 1)",
}

PHASE_CONFIRM_EVENTS: Dict[str, str] = {
    "special_attacks": "Detect the fight has started",
}

PHASE_SPECIAL_EVENTS: Dict[str, str] = {
    "battle_end": "Detect the fight has completed",
}

PHASE_TRANSITION_OVERRIDES: Dict[Tuple[str, str], str] = {
    ("BattleLoop", "Scan"): "Detect no fight remaining",
}

# Default ROIs for template matching (normalized x, y, w, h relative to frame).
NAMEPLATE_TEMPLATE_ROI: Tuple[float, float, float, float] = (0.35, 0.15, 0.32, 0.20)
ATTACK_TEMPLATE_ROI: Tuple[float, float, float, float] = (0.22, 0.10, 0.40, 0.24)


class CombatController(SkillController):
    """State machine driving combat detection and interactions."""

    name = "combat"

    def __init__(self, runtime):
        super().__init__(runtime)
        self._state = "Scan"
        self._absent_counter = 0
        self._last_log_ts = 0.0
        self._last_found: Optional[bool] = None
        self.monster_id = "twisted_wendigo"
        self.word = "Wendigo"
        self.prefix_word: Optional[str] = "Twisted"
        self.attack_word = "Attack"
        self.monster_profile: Dict[str, object] = {}
        self.interface_profile: Dict[str, object] = {}
        self.prepare_terms: List[str] = ["prepare", "choose"]
        self.weapon_digits: List[str] = ["1"]
        self.special_tokens: List[str] = ["special", "attacks"]
        self.current_phase: str = PHASE_STATE_DEFAULTS["Scan"]
        self.runtime.set_phase(self.current_phase)
        self._tile_size_px: Optional[float] = None
        self._tile_origin_px: Tuple[float, float] = (0.0, 0.0)
        self._player_tile_offset: Tuple[float, float] = (0.5, 0.5)
        self._tile_grid: Optional[TileGrid] = None
        self._grid_signature: Optional[Tuple[int, int, int, int]] = None
        self._tile_tracker = TileTracker()
        self._player_tile: Tuple[int, int] = (0, 0)
        self._last_tracked_tile: Optional[Tuple[int, int]] = None
        self._target_lock_grace = 1.2  # seconds to keep target locked after prefix disappears
        self._target_lock_until = 0.0
        self._locked_box: Optional[Tuple[int, int, int, int]] = None
        self._click_attempts: Dict[str, int] = {
            "prime_nameplate": 0,
            "attack_button": 0,
        }
        self._confidence_history: Dict[str, deque[float]] = {
            "nameplate": deque(maxlen=6),
            "attack_button": deque(maxlen=6),
        }
        self._last_transition_reason: Optional[str] = None
        self._last_nameplate_conf: float = 0.0
        self._hover_state = HoverState()
        self._floating_confidence: float = 0.0
        self._min_nameplate_conf = 0.35
        self._enable_tile_tracker = False
        self.attack_template = None
        self._template_threshold = 0.78
        self._attack_template_threshold = 0.78
        self.attack_template_path: Optional[str] = None

    # ------------------------------------------------------------------
    def on_start(self, params: Dict[str, object] | None = None) -> None:
        self._state = "Scan"
        self._absent_counter = 0
        self._last_log_ts = 0.0
        self._last_found = None
        self._target_lock_until = 0.0
        self._locked_box = None
        for key in self._click_attempts:
            self._click_attempts[key] = 0
        for hist in self._confidence_history.values():
            hist.clear()
        self._last_transition_reason = "runtime_start"
        self._last_nameplate_conf = 0.0
        self._apply_params(params or {})
        self.runtime.set_state(self._state)
        self._set_phase(PHASE_STATE_DEFAULTS["Scan"])
        self._tile_grid = None
        self._grid_signature = None
        self._tile_tracker.clear()
        self._last_tracked_tile = None
        self._hover_state.reset()
        self._floating_confidence = 0.0

    def on_stop(self) -> None:
        self._state = "Scan"
        self.runtime.set_state(self._state)
        self._set_phase(PHASE_STATE_DEFAULTS["Scan"])
        self._tile_grid = None
        self._grid_signature = None
        self._tile_tracker.clear()
        self._last_tracked_tile = None
        self._hover_state.reset()
        self._floating_confidence = 0.0

    def on_update_params(self, params: Dict[str, object] | None = None) -> None:
        if params:
            self._apply_params(params)

    def _apply_params(self, params: Dict[str, object]) -> None:
        monster_id = params.get("monster_id") or self.runtime.status.monster_id or self.monster_id
        interface_id = params.get("interface_id") or self.runtime.status.interface_id or "combat"

        monster_profile = load_monster_profile(monster_id) or {}
        interface_profile = load_interface_profile(interface_id) or {}

        word = params.get("word") or monster_profile.get("word") or self.word
        prefix = params.get("prefix_word")
        if prefix is None:
            prefix = monster_profile.get("prefix")
        attack = monster_profile.get("attack_word") or interface_profile.get("attack_word") or self.attack_word

        template_override = params.get("template_override") or params.get("template_path")
        template_default = params.get("template_default") or self.runtime.status.template_path
        template_source = "default"
        if template_override:
            template = str(template_override)
            template_source = "override"
        else:
            template = monster_profile.get("template")
            if template:
                template_source = "monster"
            else:
                template = interface_profile.get("template")
                if template:
                    template_source = "interface"
                else:
                    template = template_default
                    template_source = "default"
        if template:
            template = str(template)
        else:
            template = None
            template_source = "none"
        self.runtime.status.template_path = template
        setattr(self.runtime.status, "template_source", template_source)

        attack_template = interface_profile.get("attack_template") or monster_profile.get("attack_template")
        if params.get("attack_template"):
            attack_template = params.get("attack_template")
        thresh = params.get("template_threshold") or monster_profile.get("template_threshold") or interface_profile.get("template_threshold")
        if thresh is not None:
            try:
                self._template_threshold = float(thresh)
            except (TypeError, ValueError):
                self._template_threshold = 0.78
        attack_thresh = params.get("attack_template_threshold") or interface_profile.get("attack_template_threshold")
        if attack_thresh is not None:
            try:
                self._attack_template_threshold = float(attack_thresh)
            except (TypeError, ValueError):
                self._attack_template_threshold = 0.78
        if attack_template:
            try:
                self.attack_template = cv2.imread(attack_template, cv2.IMREAD_COLOR)
            except Exception:
                self.attack_template = None
        else:
            self.attack_template = None
        self.attack_template_path = attack_template if isinstance(attack_template, str) else None

        tile_size = params.get("tile_size_px")
        if tile_size is None:
            tile_size = self.runtime.status.tile_size_px
        try:
            self._tile_size_px = float(tile_size) if tile_size else None
        except (TypeError, ValueError):
            self._tile_size_px = None

        tile_origin = params.get("tile_origin_px") or self.runtime.status.tile_origin_px
        if isinstance(tile_origin, (list, tuple)) and len(tile_origin) == 2:
            self._tile_origin_px = (float(tile_origin[0]), float(tile_origin[1]))

        player_offset = params.get("player_tile_offset") or self.runtime.status.player_tile_offset
        if isinstance(player_offset, (list, tuple)) and len(player_offset) == 2:
            self._player_tile_offset = (float(player_offset[0]), float(player_offset[1]))

        self.monster_id = str(monster_id)
        self.word = str(word)
        self.prefix_word = str(prefix) if prefix else None
        self.attack_word = str(attack)
        self.monster_profile = monster_profile
        self.interface_profile = interface_profile
        self.prepare_terms = list(interface_profile.get("prepare_targets", self.prepare_terms)) or ["prepare", "choose"]
        self.weapon_digits = list(interface_profile.get("weapon_digits", self.weapon_digits)) or ["1"]
        self.special_tokens = list(interface_profile.get("special_tokens", self.special_tokens)) or ["special", "attacks"]

        status = self.runtime.status
        status.monster_id = self.monster_id
        status.word = self.word
        status.prefix_word = self.prefix_word
        status.interface_id = interface_id
        status.template_path = template
        self._target_lock_until = 0.0
        self._locked_box = None
        self._set_phase(PHASE_STATE_DEFAULTS.get(self._state, self.current_phase))

    def _set_phase(self, phase: str) -> None:
        if phase == self.current_phase:
            return
        self.current_phase = phase
        self.runtime.set_phase(phase)

    def process_frame(self, frame, ctx: FrameContext) -> Tuple[Dict[str, object], Optional[bytes]]:
        status = self.runtime.status
        if status.method in {"auto", "ocr"}:
            configure_tesseract(status.tesseract_path)

        now = time.time()
        self._set_phase(PHASE_STATE_DEFAULTS.get(self._state, self.current_phase))

        rx, ry = ctx.roi_origin
        rw, rh = ctx.roi_size
        roi_rect = [rx, ry, rw, rh]
        frame_h, frame_w = frame.shape[:2]
        calibration = getattr(self.runtime, "calibration", None)

        boxes: List[Tuple[int, int, int, int]] = []
        best_conf = 0.0
        method = status.method

        # Template first
        if method in {"auto", "template"} and status.template_path:
            tpl = cv2.imread(status.template_path, cv2.IMREAD_COLOR)
            if tpl is not None:
                tpl_boxes = []
                scores: List[float] = []
                nameplate_roi = NAMEPLATE_TEMPLATE_ROI
                if calibration:
                    nameplate_roi = calibration.get_roi("nameplate", NAMEPLATE_TEMPLATE_ROI)
                nx, ny, nw, nh = self._roi_pixels(frame_w, frame_h, nameplate_roi)
                if nw >= tpl.shape[1] and nh >= tpl.shape[0]:
                    roi_view = frame[ny : ny + nh, nx : nx + nw]
                    tpl_boxes, scores = detect_template_multi(roi_view, tpl, threshold=self._template_threshold)
                    tpl_boxes = [
                        (bx + nx, by + ny, bw, bh)
                        for (bx, by, bw, bh) in tpl_boxes
                    ]
                if not tpl_boxes:
                    tpl_boxes, scores = detect_template_multi(frame, tpl, threshold=self._template_threshold)
                if tpl_boxes:
                    boxes = tpl_boxes
                    best_conf = max(scores) if scores else 0.0
                    method = "template"
                    if calibration:
                        calibration.template_success(
                            "nameplate",
                            best_conf,
                            roi=nameplate_roi,
                            box=tpl_boxes[0] if tpl_boxes else None,
                        )
        # OCR fallback
        if not boxes and method in {"auto", "ocr", "template_fallback"}:
            ocr_boxes, ocr_conf = detect_word_ocr_multi(frame, target=self.word)
            if ocr_boxes:
                boxes = ocr_boxes
                method = "ocr"
                if len(boxes) > 1:
                    best_conf = 0.8
                elif ocr_conf <= 0.01:
                    best_conf = 0.5
                else:
                    best_conf = ocr_conf
                if calibration and status.template_path and best_conf >= self._min_nameplate_conf:
                    calibration.template_fallback(
                        "nameplate",
                        frame.copy(),
                        template_path=status.template_path,
                        hint_box=boxes[0],
                        confidence=best_conf,
                        state=self._state,
                        phase=self.current_phase,
                        roi_rect=roi_rect,
                        boxes=boxes,
                    )

        attack_boxes: List[Tuple[int, int, int, int]] = []
        attack_conf = 0.0
        attack_source: Optional[str] = None

        prefix_boxes: List[Tuple[int, int, int, int]] = []
        prefix_conf = 0.0
        if self.prefix_word:
            prefix_boxes, prefix_conf = detect_word_ocr_multi(frame, target=self.prefix_word)

        # Focused HUD regions ------------------------------------------------
        attack_roi_norm = ATTACK_TEMPLATE_ROI
        if calibration:
            attack_roi_norm = calibration.get_roi("attack", ATTACK_TEMPLATE_ROI)
        apx, apy, apw, aph = self._roi_pixels(frame_w, frame_h, attack_roi_norm)
        attack_panel_roi = frame[apy:apy + aph, apx:apx + apw]
        if attack_panel_roi.size == 0:
            apx = int(0.55 * frame_w)
            apy = int(0.20 * frame_h)
            apw = int(0.40 * frame_w)
            aph = int(0.60 * frame_h)
            attack_panel_roi = frame[apy:apy + aph, apx:apx + apw]

        ppx = int(0.55 * frame_w)
        ppy = int(0.07 * frame_h)
        ppw = int(0.43 * frame_w)
        pph = int(0.86 * frame_h)
        bbx = int(0.10 * frame_w)
        bby = int(0.83 * frame_h)
        bbw = int(0.80 * frame_w)
        bbh = int(0.15 * frame_h)
        # R1 focus: limit to monster + attack only for now
        # prepare_panel_roi = frame[ppy:ppy + pph, ppx:ppx + ppw]
        # bottom_bar_roi = frame[bby:bby + bbh, bbx:bbx + bbw]

        # Disable downstream detections until those phases are implemented
        prepare_boxes: List[Tuple[int, int, int, int]] = []
        prepare_conf = 0.0
        spec_boxes: List[Tuple[int, int, int, int]] = []
        atks_boxes: List[Tuple[int, int, int, int]] = []
        special_attacks_present = False
        special_attacks_conf = 0.0
        digit_boxes: List[Tuple[int, int, int, int]] = []
        digit_conf = 0.0

        raw_nameplate_boxes = list(boxes)
        prefix_present = bool(prefix_boxes)
        lock_active = now < self._target_lock_until

        if self.prefix_word and prefix_present and raw_nameplate_boxes:
            bx, by, bw, bh = raw_nameplate_boxes[0]
            px, py, pw, ph = prefix_boxes[0]
            nx0 = min(px, bx)
            ny0 = min(py, by)
            nx1 = max(px + pw, bx + bw)
            ny1 = max(py + ph, by + bh)
            combined = (nx0, ny0, nx1 - nx0, ny1 - ny0)
            boxes = [combined]
            self._locked_box = combined
            self._target_lock_until = now + self._target_lock_grace
            lock_active = True
            best_conf = min(best_conf, prefix_conf) if best_conf > 0 and prefix_conf > 0 else max(best_conf, prefix_conf)
        elif lock_active and self._locked_box:
            if not boxes:
                boxes = [self._locked_box]
            if best_conf <= 0.0:
                if self._confidence_history["nameplate"]:
                    best_conf = self._confidence_history["nameplate"][-1]
                else:
                    best_conf = self._last_nameplate_conf
        else:
            if not prefix_present and best_conf < self._min_nameplate_conf:
                self._locked_box = None
            if not raw_nameplate_boxes:
                self._target_lock_until = 0.0
                lock_active = False

        # Allow an OCR lock without prefix when confidence is high enough
        if not lock_active and best_conf >= (self._min_nameplate_conf + 0.1):
            self._locked_box = boxes[0] if boxes else None
            self._target_lock_until = now + self._target_lock_grace
            lock_active = True

        if raw_nameplate_boxes:
            self._confidence_history["nameplate"].append(best_conf)
            self._last_nameplate_conf = best_conf

        if attack_boxes:
            self._confidence_history["attack_button"].append(attack_conf)

        lock_remaining = max(0.0, self._target_lock_until - now)

        target_ready = bool(boxes) and best_conf >= self._min_nameplate_conf and (prefix_present or lock_active)

        tracker_info: Optional[Dict[str, object]] = None
        attack_context_rect: Optional[Tuple[int, int, int, int]] = None
        floating_boxes: List[Tuple[int, int, int, int]] = []
        floating_conf = 0.0
        world_tile: Optional[Tuple[int, int]] = None
        if self._enable_tile_tracker and self._tile_size_px and self._tile_size_px > 0:
            if self._tile_grid is None or self._grid_signature != (rx, ry, rw, rh):
                self._tile_grid = TileGrid(
                    self._tile_size_px,
                    roi_origin=(rx, ry),
                    tile_origin=self._tile_origin_px,
                    hover_offset=self._player_tile_offset,
                )
                self._grid_signature = (rx, ry, rw, rh)
                self._player_tile = self._tile_grid.player_tile(rw, rh)
            grid = self._tile_grid
            if grid:
                timestamp = now
                track = None
                if boxes and best_conf >= self._min_nameplate_conf:
                    bx, by, bw, bh = boxes[0]
                    center_x = rx + bx + bw / 2
                    center_y = ry + by + bh / 2
                    row, col = grid.screen_to_tile(center_x, center_y)
                    track = self._tile_tracker.update(self.monster_id, row, col, best_conf, timestamp=timestamp)
                else:
                    self._tile_tracker.mark_missed(self.monster_id)
                    track = self._tile_tracker.predict(self.monster_id, timestamp=timestamp)
                self._tile_tracker.prune()
                if track:
                    tracker_tile = (track.row, track.col)
                    if tracker_tile != self._last_tracked_tile:
                        if self._last_tracked_tile is not None:
                            self.runtime.emit_event(
                                "transition",
                                "tile_move",
                                [0, 0, 0, 0],
                                [],
                                0.0,
                                state=self._state,
                                phase=self.current_phase,
                                notes=f"{self._last_tracked_tile}->{tracker_tile}",
                            )
                        self._last_tracked_tile = tracker_tile
                    adjacent = TileGrid.is_adjacent(self._player_tile, tracker_tile)
                    base_world = self.runtime.status.world_tile if hasattr(self.runtime.status, "world_tile") else None
                    if base_world and isinstance(base_world, (list, tuple)) and len(base_world) == 2:
                        try:
                            world_tile = (
                                int(base_world[0] + (track.row - self._player_tile[0])),
                                int(base_world[1] + (track.col - self._player_tile[1])),
                            )
                        except Exception:
                            world_tile = None
                    attack_context_rect = grid.context_menu_rect(track.row, track.col)
                    if adjacent:
                        if self._hover_state.tile != tracker_tile:
                            self._hover_state.tile = tracker_tile
                            self._hover_state.confirmed = True
                            self._hover_state.attempts = 0
                        self._hover_state.active = True
                    else:
                        self._hover_state.reset()
                    if attack_context_rect:
                        ax, ay, aw, ah = attack_context_rect
                        ax0 = max(0, ax)
                        ay0 = max(0, ay)
                        ax1 = min(rw, ax + aw)
                        ay1 = min(rh, ay + ah)
                        if ax1 > ax0 and ay1 > ay0:
                            menu_roi = frame[ay0:ay1, ax0:ax1]
                            local_boxes, local_conf = detect_word_ocr_multi(menu_roi, target=self.attack_word)
                            attack_boxes = [
                                (bx + ax0, by + ay0, bw, bh)
                                for (bx, by, bw, bh) in local_boxes
                            ]
                            if attack_boxes:
                                attack_source = "ocr_context"
                                attack_conf = local_conf if local_conf > 0.01 else 0.6
                        if not attack_boxes and self.attack_template is not None:
                            search_regions: List[Tuple[str, np.ndarray, Tuple[int, int]]] = []
                            if attack_panel_roi.size > 0:
                                search_regions.append(("template_roi", attack_panel_roi, (apx, apy)))
                            search_regions.append(("template", frame, (0, 0)))
                            for region_label, region_img, (ox, oy) in search_regions:
                                tpl_boxes, scores = detect_template_multi(
                                    region_img,
                                    self.attack_template,
                                    threshold=self._attack_template_threshold,
                                )
                                if tpl_boxes:
                                    attack_boxes = [
                                        (bx + ox, by + oy, bw, bh)
                                        for (bx, by, bw, bh) in tpl_boxes
                                    ]
                                    attack_source = region_label
                                    attack_conf = max(scores) if scores else 0.7
                                    break
                    # Fallback to static HUD band on the right-hand side
                    if not attack_boxes:
                        local_boxes, local_conf = detect_word_ocr_multi(attack_panel_roi, target=self.attack_word)
                        if local_boxes:
                            attack_boxes = [
                                (bx + apx, by + apy, bw, bh)
                                for (bx, by, bw, bh) in local_boxes
                            ]
                            attack_source = "ocr_panel"
                            attack_conf = local_conf if local_conf > 0.01 else 0.6
                    # Global fallback: scan the whole combat frame for the attack button
                    if not attack_boxes:
                        global_boxes, global_conf = detect_word_ocr_multi(frame, target=self.attack_word)
                        filtered: List[Tuple[int, int, int, int]] = []
                        for (bx, by, bw, bh) in global_boxes:
                            if bh < 15 or bw < 60:
                                continue
                            if by < int(0.15 * rh):
                                continue
                            filtered.append((bx, by, bw, bh))
                        if filtered:
                            attack_boxes = filtered
                            attack_source = "ocr_global"
                            attack_conf = global_conf if global_conf > 0.01 else 0.6
                    tracker_info = {
                        "row": track.row,
                        "col": track.col,
                        "adjacent": adjacent,
                        "player_tile": list(self._player_tile),
                        "confidence": track.confidence,
                        "velocity": [track.vx, track.vy],
                        "hover_confirmed": bool(self._hover_state.confirmed),
                        "world_tile": list(world_tile) if world_tile else None,
                        "floating_confidence": self._floating_confidence,
                    }
                else:
                    self._hover_state.reset()
                    self._floating_confidence = 0.0
        else:
            self._hover_state.reset()
            self._floating_confidence = 0.0

        planned_clicks: List[PlannedClick] = []
        if attack_boxes and attack_source and attack_source.startswith("template") and calibration:
            attack_roi_norm_to_log = attack_roi_norm if 'attack_roi_norm' in locals() else ATTACK_TEMPLATE_ROI
            calibration.template_success(
                "attack",
                attack_conf,
                roi=attack_roi_norm_to_log,
                box=attack_boxes[0],
            )
        elif (
            attack_boxes
            and attack_source
            and attack_source.startswith("ocr")
            and calibration
            and self.attack_template_path
        ):
            calibration.template_fallback(
                "attack",
                frame.copy(),
                template_path=self.attack_template_path,
                hint_box=attack_boxes[0],
                confidence=attack_conf,
                state=self._state,
                phase=self.current_phase,
                roi_rect=roi_rect,
                boxes=attack_boxes,
            )
        if target_ready and boxes:
            bx, by, bw, bh = boxes[0]
            cx = rx + bx + bw // 2
            cy = ry + by + int(1.4 * bh)
            planned_clicks.append(PlannedClick(cx, cy, "prime_nameplate"))
        if attack_boxes:
            planned_clicks.append(self._adjust_attack_click(attack_boxes[0], (rx, ry), attack_source))
            self._confidence_history["attack_button"].append(attack_conf)
        else:
            self._floating_confidence = floating_conf if floating_conf > 0 else self._floating_confidence
        # Do not plan weapon clicks until that phase is implemented

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
            prefix_boxes,
            prefix_conf,
            roi_rect,
            lock_active,
            prefix_present,
            lock_remaining,
        )
        self._advance_state(target_ready, attack_boxes, prepare_boxes, digit_boxes, special_attacks_present, planned_clicks, roi_rect, lock_active, prefix_present)

        annotated = frame.copy()
        nameplate_color = (0, 0, 255)
        nameplate_label = "OCR"
        if method and method.startswith("template"):
            nameplate_color = (180, 0, 255)
            nameplate_label = "TPL"
        for (bx, by, bw, bh) in boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), nameplate_color, 2)
            cv2.putText(
                annotated,
                nameplate_label,
                (bx, max(12, by - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                nameplate_color,
                1,
                cv2.LINE_AA,
            )
        attack_color = (0, 255, 0)
        attack_label = "OCR"
        if attack_source and attack_source.startswith("template"):
            attack_color = (0, 255, 255)
            attack_label = "TPL"
        elif attack_source == "ocr_context":
            attack_label = "OCR ctx"
        elif attack_source == "ocr_panel":
            attack_label = "OCR panel"
        elif attack_source == "ocr_global":
            attack_label = "OCR global"
        for (bx, by, bw, bh) in attack_boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), attack_color, 2)
            cv2.putText(
                annotated,
                attack_label,
                (bx, max(12, by - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                attack_color,
                1,
                cv2.LINE_AA,
            )
        for (bx, by, bw, bh) in floating_boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (255, 128, 0), 1)
        for (bx, by, bw, bh) in prepare_boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (255, 0, 0), 2)
        for (bx, by, bw, bh) in spec_boxes + atks_boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)
        for (bx, by, bw, bh) in digit_boxes:
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (255, 255, 0), 2)
        if attack_context_rect:
            ax, ay, aw, ah = attack_context_rect
            cv2.rectangle(annotated, (ax, ay), (ax + aw, ay + ah), (255, 0, 255), 1)
        for planned in planned_clicks:
            fx = planned.x - rx
            fy = planned.y - ry
            color = (255, 0, 255)
            if planned.label == "attack_button":
                color = (0, 255, 255) if planned.source == "template" else (0, 128, 255)
            cv2.drawMarker(annotated, (int(fx), int(fy)), color, markerType=cv2.MARKER_CROSS, markerSize=12, thickness=2)
            cv2.circle(annotated, (int(fx), int(fy)), 14, color, 1)
            label_text = planned.label.replace("_", " ")
            cv2.putText(
                annotated,
                label_text,
                (int(fx) + 8, int(fy) + 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )

        # Overlay recent real clicks (within ~1s)
        for click in self.runtime.get_recent_clicks():
            cx = int(click.get("x", 0)) - rx
            cy = int(click.get("y", 0)) - ry
            if cx < 0 or cy < 0 or cx >= rw or cy >= rh:
                continue
            cv2.circle(annotated, (cx, cy), 16, (0, 165, 255), 3)
            cv2.circle(annotated, (cx, cy), 4, (0, 165, 255), -1)
            label = click.get("label", "")
            if label:
                cv2.putText(
                    annotated,
                    label,
                    (cx + 10, cy - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 165, 255),
                    1,
                    cv2.LINE_AA,
                )

        ok, jpg = cv2.imencode(
            ".jpg",
            annotated,
            [int(cv2.IMWRITE_JPEG_QUALITY), 70],
        )
        preview = jpg.tobytes() if ok else None

        count = len(boxes)
        if target_ready and raw_nameplate_boxes:
            status.total_detections += len(raw_nameplate_boxes)

        result = {
            "found": target_ready,
            "count": count,
            "confidence": best_conf,
            "method": method,
            "boxes": boxes,
            "attack": {
                "found": bool(attack_boxes),
                "count": len(attack_boxes),
                "confidence": attack_conf,
                "boxes": attack_boxes,
                "word": self.attack_word,
                "source": attack_source,
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
            "prefix": {
                "found": bool(prefix_boxes),
                "count": len(prefix_boxes),
                "confidence": prefix_conf,
                "boxes": prefix_boxes,
                "word": self.prefix_word,
            },
            "hover": {
                "active": bool(self._hover_state.active) if self._hover_state else False,
                "confirmed": bool(self._hover_state.confirmed) if self._hover_state else False,
                "tile": list(self._hover_state.tile) if self._hover_state.tile else None,
                "attempts": self._hover_state.attempts,
                "floating_confidence": self._floating_confidence,
                "boxes": floating_boxes,
            },
            "target_lock": {
                "active": bool(lock_active),
                "remaining_s": lock_remaining,
                "grace_s": self._target_lock_grace,
            },
            "tile_tracker": tracker_info,
            "attack_menu_rect": attack_context_rect,
            "click_attempts": dict(self._click_attempts),
            "confidence_history": {
                "nameplate": list(self._confidence_history["nameplate"]),
                "attack_button": list(self._confidence_history["attack_button"]),
            },
            "planned_clicks": [
                {"x": planned.x, "y": planned.y, "label": planned.label, "action": planned.action}
                for planned in planned_clicks
            ],
            "total_detections": status.total_detections,
            "roi": roi_rect,
            "state": self._state,
            "monster_id": self.monster_id,
            "phase": self.current_phase,
            "transition_reason": self._last_transition_reason,
        }

        self._log_detection(target_ready, count, best_conf, method, attack_boxes, attack_conf, prepare_boxes, prepare_conf, special_attacks_present, special_attacks_conf, digit_boxes, digit_conf, prefix_boxes, prefix_conf)
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
        prefix_boxes,
        prefix_conf,
        roi_rect,
        lock_active: bool,
        prefix_present: bool,
        lock_remaining: float,
    ) -> None:
        should_emit_nameplate = bool(boxes) and (not self.prefix_word or prefix_present or lock_active)
        if should_emit_nameplate:
            self._set_phase(PHASE_DETECT_EVENTS["nameplate"])
            phase_label = PHASE_DETECT_EVENTS["nameplate"]
            notes = (
                f"{phase_label} | lock={int(lock_active)} remaining={lock_remaining:.2f}s "
                f"prefix={int(prefix_present)} prime_attempts={self._click_attempts.get('prime_nameplate', 0)}"
            )
            self.runtime.emit_event("detect", "nameplate", roi_rect, boxes, best_conf, state=self._state, phase=self.current_phase, notes=notes)
        if attack_boxes:
            self._set_phase(PHASE_DETECT_EVENTS["attack_button"])
            phase_label = PHASE_DETECT_EVENTS["attack_button"]
            notes = (
                f"{phase_label} | lock={int(lock_active)} remaining={lock_remaining:.2f}s "
                f"attack_attempts={self._click_attempts.get('attack_button', 0)}"
            )
            self.runtime.emit_event("detect", "attack_button", roi_rect, attack_boxes, attack_conf, state=self._state, phase=self.current_phase, notes=notes)
        # Suppress prepare/weapon/special events for now

    def _increment_click_attempt(self, label: str) -> None:
        self._click_attempts[label] = self._click_attempts.get(label, 0) + 1

    def _advance_state(
        self,
        target_ready: bool,
        attack_boxes,
        prepare_boxes,
        digit_boxes,
        special_attacks_present,
        planned_clicks: List[PlannedClick],
        roi_rect,
        lock_active: bool,
        prefix_present: bool,
    ) -> None:
        runtime = self.runtime
        click_tuples = [pc.to_tuple() for pc in planned_clicks]

        if self._hover_state and any(pc.label == "hover_tile" and pc.action == "hover" for pc in planned_clicks):
            now = time.time()
            if now - self._hover_state.last_hover_ts > 0.3:
                runtime.emit_click(
                    click_tuples,
                    "hover_tile",
                    state=self._state,
                    phase=self.current_phase,
                    notes=self.current_phase,
                )
                self._hover_state.last_hover_ts = now
                self._hover_state.attempts += 1

        if self._state == "Scan":
            if target_ready:
                self._increment_click_attempt("prime_nameplate")
                self._set_phase(PHASE_CLICK_EVENTS["prime_nameplate"])
                runtime.emit_click(
                    click_tuples,
                    "prime_nameplate",
                    state=self._state,
                    phase=self.current_phase,
                    notes=self.current_phase,
                )
                self._transition("PrimeTarget", notes="nameplate locked")
        elif self._state == "PrimeTarget":
            if attack_boxes:
                self._increment_click_attempt("attack_button")
                self._set_phase(PHASE_CLICK_EVENTS["attack_button"])
                runtime.emit_click(
                    click_tuples,
                    "attack_button",
                    state=self._state,
                    phase=self.current_phase,
                    notes=self.current_phase,
                )
                self._transition("AttackPanel", notes="attack detected")
            elif target_ready:
                self._increment_click_attempt("prime_nameplate")
                self._set_phase(PHASE_CLICK_EVENTS["prime_nameplate"])
                runtime.emit_click(
                    click_tuples,
                    "prime_nameplate",
                    state=self._state,
                    phase=self.current_phase,
                    notes=self.current_phase,
                )
            else:
                if lock_active:
                    reason = "target lost (lock active but no nameplate)"
                elif prefix_present:
                    reason = "target lost (nameplate hidden)"
                else:
                    reason = "target lost (lock expired)"
                self._transition("Scan", notes=reason)
        elif self._state == "AttackPanel":
            if attack_boxes:
                self._increment_click_attempt("attack_button")
                self._set_phase(PHASE_CLICK_EVENTS["attack_button"])
                runtime.emit_click(
                    click_tuples,
                    "attack_button",
                    state=self._state,
                    phase=self.current_phase,
                    notes=self.current_phase,
                )
            elif prepare_boxes:
                self._transition("Prepare", notes="prepare detected")
            else:
                self._transition("Scan", notes="attack button missing")
        elif self._state == "Prepare":
            if digit_boxes:
                self._set_phase(PHASE_CLICK_EVENTS["weapon_1"])
                runtime.emit_click(
                    click_tuples,
                    "weapon_1",
                    state=self._state,
                    phase=self.current_phase,
                    notes=self.current_phase,
                )
                self._transition("Weapon", notes="weapon digit detected")
            elif not prepare_boxes:
                self._transition("Scan", notes="prepare panel missing")
        elif self._state == "Weapon":
            if special_attacks_present:
                self._transition("BattleLoop", notes="special attacks active")
            elif not digit_boxes:
                self._transition("Scan", notes="weapon digit missing")
        elif self._state == "BattleLoop":
            if special_attacks_present:
                self._absent_counter = 0
            else:
                self._absent_counter += 1
                if self._absent_counter >= 6:
                    self._set_phase(PHASE_SPECIAL_EVENTS["battle_end"])
                    notes = f"{PHASE_SPECIAL_EVENTS['battle_end']} | absent M=6 frames"
                    runtime.emit_event("transition", "battle_end", roi_rect, [], 0.0, state=self._state, phase=self.current_phase, notes=notes)
                    self._transition("Scan", notes="battle loop ended (missing cues)")

    def _transition(self, new_state: str, *, notes: Optional[str] = None) -> None:
        prev = self._state
        self._state = new_state
        if new_state != "BattleLoop":
            self._absent_counter = 0
        phase = PHASE_TRANSITION_OVERRIDES.get((prev, new_state), PHASE_STATE_DEFAULTS.get(new_state, self.current_phase))
        self._set_phase(phase)
        self.runtime.set_state(new_state)
        self._last_transition_reason = notes or ""
        if new_state == "Scan":
            self._target_lock_until = 0.0
            self._locked_box = None
            for key in self._click_attempts:
                self._click_attempts[key] = 0
        self.runtime.emit_event(
            "transition",
            f"{prev}->{new_state}",
            [0, 0, 0, 0],
            [],
            0.0,
            state=new_state,
            phase=self.current_phase,
            notes=notes,
        )

    def _log_detection(self, found: bool, count: int, best_conf: float, method: str, attack_boxes, attack_conf, prepare_boxes, prepare_conf, special_attacks_present: bool, special_attacks_conf: float, digit_boxes, digit_conf, prefix_boxes, prefix_conf) -> None:
        now = time.time()
        if self._last_found is not found or now - self._last_log_ts > 2.0:
            lock_active = now < self._target_lock_until
            lock_remaining = max(0.0, self._target_lock_until - now)
            self.runtime.logger.info(
                "detect | phase=%s found=%s count=%d conf=%.3f method=%s lock_active=%s lock_rem=%.2f",
                self.current_phase,
                found,
                count,
                best_conf,
                method,
                lock_active,
                lock_remaining,
            )
            if attack_boxes:
                self.runtime.logger.info(
                    "detect_attack | phase=%s count=%d conf=%.3f attempts=%d",
                    self.current_phase,
                    len(attack_boxes),
                    attack_conf,
                    self._click_attempts.get("attack_button", 0),
                )
            if prepare_boxes:
                self.runtime.logger.info(
                    "detect_prepare | phase=%s count=%d conf=%.3f",
                    self.current_phase,
                    len(prepare_boxes),
                    prepare_conf,
                )
            if special_attacks_present:
                self.runtime.logger.info(
                    "detect_special_attacks | phase=%s conf=%.3f",
                    self.current_phase,
                    special_attacks_conf,
                )
            if digit_boxes:
                self.runtime.logger.info(
                    "detect_weapon_1 | phase=%s count=%d conf=%.3f",
                    self.current_phase,
                    len(digit_boxes),
                    digit_conf,
                )
            if prefix_boxes:
                self.runtime.logger.info(
                    "detect_prefix | phase=%s count=%d conf=%.3f",
                    self.current_phase,
                    len(prefix_boxes),
                    prefix_conf,
                )
            if self._click_attempts.get("prime_nameplate", 0) or self._click_attempts.get("attack_button", 0):
                self.runtime.logger.info(
                    "click_attempts | phase=%s prime=%d attack=%d",
                    self.current_phase,
                    self._click_attempts.get("prime_nameplate", 0),
                    self._click_attempts.get("attack_button", 0),
                )
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

    @staticmethod
    def _roi_pixels(width: int, height: int, rel: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
        rx, ry, rw, rh = rel
        x = int(round(rx * width))
        y = int(round(ry * height))
        w_px = max(1, int(round(rw * width)))
        h_px = max(1, int(round(rh * height)))
        if x < 0:
            x = 0
        if y < 0:
            y = 0
        if x >= width:
            x = width - 1
        if y >= height:
            y = height - 1
        if x + w_px > width:
            w_px = max(1, width - x)
        if y + h_px > height:
            h_px = max(1, height - y)
        return x, y, w_px, h_px

    # Utilities -----------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state
    def _adjust_attack_click(
        self,
        box: Tuple[int, int, int, int],
        roi_origin: Tuple[int, int],
        source: Optional[str],
    ) -> PlannedClick:
        bx, by, bw, bh = box
        adj_x = bx + bw // 2
        adj_y = by + bh // 2
        if source and source.startswith("ocr"):
            hx, hy, hw, hh = derive_hitbox_from_word((bx, by, bw, bh))
            if hw > 0 and hh > 0:
                adj_x = hx + hw // 2
                adj_y = hy + hh // 2
        return PlannedClick(
            roi_origin[0] + adj_x,
            roi_origin[1] + adj_y,
            "attack_button",
            source=source or "",
        )
