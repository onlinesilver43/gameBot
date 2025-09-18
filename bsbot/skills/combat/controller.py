from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from bsbot.skills.base import FrameContext, SkillController
from bsbot.core.config import load_monster_profile, load_interface_profile
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

    def on_stop(self) -> None:
        self._state = "Scan"
        self.runtime.set_state(self._state)
        self._set_phase(PHASE_STATE_DEFAULTS["Scan"])

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

        template = params.get("template_path")
        if template is None:
            template = monster_profile.get("template") or interface_profile.get("template") or self.runtime.status.template_path

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
            boxes, best_conf = detect_word_ocr_multi(frame, target=self.word)
            if method == "auto":
                method = "ocr_fallback"
            else:
                method = "ocr"

        attack_boxes, attack_conf = detect_word_ocr_multi(frame, target=self.attack_word)

        prefix_boxes: List[Tuple[int, int, int, int]] = []
        prefix_conf = 0.0
        if self.prefix_word:
            prefix_boxes, prefix_conf = detect_word_ocr_multi(frame, target=self.prefix_word)

        # Focused HUD regions ------------------------------------------------
        apx, apy = int(0.55 * rw), int(0.20 * rh)
        apw, aph = int(0.40 * rw), int(0.60 * rh)
        ppx, ppy = int(0.55 * rw), int(0.07 * rh)
        ppw, pph = int(0.43 * rw), int(0.86 * rh)
        bbx, bby = int(0.10 * rw), int(0.83 * rh)
        bbw, bbh = int(0.80 * rw), int(0.15 * rh)

        attack_panel_roi = frame[apy:apy + aph, apx:apx + apw]
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
            if not prefix_present:
                self._locked_box = None
            if not raw_nameplate_boxes:
                self._target_lock_until = 0.0
                lock_active = False

        if raw_nameplate_boxes:
            self._confidence_history["nameplate"].append(best_conf)
            self._last_nameplate_conf = best_conf

        if attack_boxes:
            self._confidence_history["attack_button"].append(attack_conf)

        lock_remaining = max(0.0, self._target_lock_until - now)

        target_ready = bool(boxes) and (not self.prefix_word or prefix_present or lock_active)

        planned_clicks: List[PlannedClick] = []
        if target_ready and boxes:
            bx, by, bw, bh = boxes[0]
            cx = rx + bx + bw // 2
            cy = ry + by + int(1.4 * bh)
            planned_clicks.append(PlannedClick(cx, cy, "prime_nameplate"))
        if attack_boxes:
            bx, by, bw, bh = attack_boxes[0]
            cx = rx + bx + bw // 2
            cy = ry + by + bh // 2
            planned_clicks.append(PlannedClick(cx, cy, "attack_button"))
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
            "target_lock": {
                "active": bool(lock_active),
                "remaining_s": lock_remaining,
                "grace_s": self._target_lock_grace,
            },
            "click_attempts": dict(self._click_attempts),
            "confidence_history": {
                "nameplate": list(self._confidence_history["nameplate"]),
                "attack_button": list(self._confidence_history["attack_button"]),
            },
            "planned_clicks": [
                {"x": planned.x, "y": planned.y, "label": planned.label}
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
            notes = (
                f"lock={int(lock_active)} remaining={lock_remaining:.2f}s prefix={int(prefix_present)} "
                f"prime_attempts={self._click_attempts.get('prime_nameplate', 0)}"
            )
            self.runtime.emit_event("detect", "nameplate", roi_rect, boxes, best_conf, state=self._state, phase=self.current_phase, notes=notes)
        if attack_boxes:
            self._set_phase(PHASE_DETECT_EVENTS["attack_button"])
            notes = (
                f"lock={int(lock_active)} remaining={lock_remaining:.2f}s "
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

        if self._state == "Scan":
            if target_ready:
                self._increment_click_attempt("prime_nameplate")
                self._set_phase(PHASE_CLICK_EVENTS["prime_nameplate"])
                runtime.emit_click(click_tuples, "prime_nameplate", state=self._state, phase=self.current_phase)
                self._transition("PrimeTarget", notes="nameplate locked")
        elif self._state == "PrimeTarget":
            if attack_boxes:
                self._increment_click_attempt("attack_button")
                self._set_phase(PHASE_CLICK_EVENTS["attack_button"])
                runtime.emit_click(click_tuples, "attack_button", state=self._state, phase=self.current_phase)
                self._transition("AttackPanel", notes="attack detected")
            elif target_ready:
                self._increment_click_attempt("prime_nameplate")
                self._set_phase(PHASE_CLICK_EVENTS["prime_nameplate"])
                runtime.emit_click(click_tuples, "prime_nameplate", state=self._state, phase=self.current_phase)
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
                runtime.emit_click(click_tuples, "attack_button", state=self._state, phase=self.current_phase)
            elif prepare_boxes:
                self._transition("Prepare", notes="prepare detected")
            else:
                self._transition("Scan", notes="attack button missing")
        elif self._state == "Prepare":
            if digit_boxes:
                self._set_phase(PHASE_CLICK_EVENTS["weapon_1"])
                runtime.emit_click(click_tuples, "weapon_1", state=self._state, phase=self.current_phase)
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
                    runtime.emit_event("transition", "battle_end", roi_rect, [], 0.0, state=self._state, phase=self.current_phase, notes="absent M=6 frames")
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

    # Utilities -----------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state
