from __future__ import annotations

import time
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

    # ------------------------------------------------------------------
    def on_start(self, params: Dict[str, object] | None = None) -> None:
        self._state = "Scan"
        self._absent_counter = 0
        self._last_log_ts = 0.0
        self._last_found = None
        self._apply_params(params or {})
        self.runtime.set_state(self._state)

    def on_stop(self) -> None:
        self._state = "Scan"
        self.runtime.set_state(self._state)

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
        prepare_panel_roi = frame[ppy:ppy + pph, ppx:ppx + ppw]
        bottom_bar_roi = frame[bby:bby + bbh, bbx:bbx + bbw]

        prepare_boxes: List[Tuple[int, int, int, int]] = []
        prepare_conf = 0.0
        for term in self.prepare_terms:
            term_boxes, term_conf = detect_word_ocr_multi(prepare_panel_roi, target=term)
            if term_boxes:
                prepare_conf = max(prepare_conf, term_conf)
                prepare_boxes.extend((ppx + bx, ppy + by, bw, bh) for (bx, by, bw, bh) in term_boxes)

        spec_boxes: List[Tuple[int, int, int, int]] = []
        atks_boxes: List[Tuple[int, int, int, int]] = []
        special_attacks_conf = 0.0
        if self.special_tokens:
            spec_local, spec_conf = detect_word_ocr_multi(bottom_bar_roi, target=self.special_tokens[0])
            spec_boxes = [(bbx + bx, bby + by, bw, bh) for (bx, by, bw, bh) in spec_local]
            special_attacks_conf = spec_conf
            if len(self.special_tokens) > 1:
                atk_local, atk_conf = detect_word_ocr_multi(bottom_bar_roi, target=self.special_tokens[1])
                atks_boxes = [(bbx + bx, bby + by, bw, bh) for (bx, by, bw, bh) in atk_local]
                if spec_boxes and atks_boxes:
                    special_attacks_conf = min(spec_conf, atk_conf)
            else:
                atks_boxes = spec_boxes
        special_attacks_present = bool(spec_boxes) and bool(atks_boxes)

        weapons_roi = self._subroi(prepare_panel_roi, (0.0, 0.50, 1.0, 0.50))
        digit_boxes_local, digit_conf = detect_digits_ocr_multi(weapons_roi, targets=tuple(self.weapon_digits))
        wpx = ppx
        wpy = ppy + int(0.50 * pph)
        digit_boxes = [(wpx + bx, wpy + by, bw, bh) for (bx, by, bw, bh) in digit_boxes_local]

        prefix_ok = not self.prefix_word or bool(prefix_boxes)
        target_ready = bool(boxes) and prefix_ok

        planned_clicks: List[PlannedClick] = []
        if target_ready:
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
            prefix_boxes,
            prefix_conf,
            roi_rect,
        )
        self._advance_state(target_ready, attack_boxes, prepare_boxes, digit_boxes, special_attacks_present, planned_clicks, roi_rect)

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

        ok, jpg = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        preview = jpg.tobytes() if ok else None

        count = len(boxes)
        if target_ready and count:
            status.total_detections += count

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
            "planned_clicks": [
                {"x": planned.x, "y": planned.y, "label": planned.label}
                for planned in planned_clicks
            ],
            "total_detections": status.total_detections,
            "roi": roi_rect,
            "state": self._state,
            "monster_id": self.monster_id,
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
    ) -> None:
        if boxes:
            self.runtime.emit_event("detect", "nameplate", roi_rect, boxes, best_conf, state=self._state)
        if attack_boxes:
            self.runtime.emit_event("detect", "attack_button", roi_rect, attack_boxes, attack_conf, state=self._state)
        if prefix_boxes:
            self.runtime.emit_event("detect", "name_prefix", roi_rect, prefix_boxes, prefix_conf, state=self._state)
        if prepare_boxes:
            self.runtime.emit_event("detect", "prepare_header", roi_rect, prepare_boxes, prepare_conf, state=self._state)
        if special_attacks_present:
            combined = spec_boxes + atks_boxes
            self.runtime.emit_event("confirm", "special_attacks", roi_rect, combined, special_attacks_conf, state=self._state)
        if digit_boxes:
            self.runtime.emit_event("detect", "weapon_slot_1", roi_rect, digit_boxes, digit_conf, state=self._state)

    def _advance_state(
        self,
        target_ready: bool,
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
            if target_ready:
                runtime.emit_click(click_tuples, "prime_nameplate", state=self._state)
                self._transition("PrimeTarget")
        elif self._state == "PrimeTarget":
            if attack_boxes:
                runtime.emit_click(click_tuples, "attack_button", state=self._state)
                self._transition("AttackPanel")
            elif not target_ready:
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

    def _log_detection(self, found: bool, count: int, best_conf: float, method: str, attack_boxes, attack_conf, prepare_boxes, prepare_conf, special_attacks_present: bool, special_attacks_conf: float, digit_boxes, digit_conf, prefix_boxes, prefix_conf) -> None:
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
            if prefix_boxes:
                self.runtime.logger.info("detect_prefix | found=True count=%d conf=%.3f", len(prefix_boxes), prefix_conf)
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
