from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple, List

import cv2
import os

from bsbot.platform.win32 import window as win
from bsbot.platform import capture
from bsbot.vision.detect import (
    detect_word_ocr,
    detect_with_template,
    configure_tesseract,
    detect_word_ocr_multi,
    ocr_find_words,
    ocr_find_tokens,
    detect_attack_button_boxes,
    find_leftmost_count_marker,
)
from bsbot.core.logging import init_logging
from bsbot.core.timeline import timeline
from bsbot.platform.input import click_screen
from bsbot.core.hysteresis import StateHysteresis, StateEvidence
from bsbot.vision.state_evidence import compute_evidence
from bsbot.core.session import SessionRecorder


@dataclass
class DetectionStatus:
    running: bool = False
    paused: bool = False
    last_result: dict = field(default_factory=dict)
    last_frame: Optional[bytes] = None  # JPEG bytes for preview
    template_path: Optional[str] = None
    title: str = "Brighter Shores"
    word: str = "Wendigo"
    tesseract_path: Optional[str] = None
    method: str = "auto"  # auto, template, ocr
    roi: Tuple[float, float, float, float] = (0.2, 0.25, 0.6, 0.5)  # relative ROI
    total_detections: int = 0
    # R1 options
    real_inputs: bool = False
    preferred_weapon: int = 1
    # Internal runtime fields for UI
    state: str = "scan"
    preview_mode: str = "full"  # full|roi


class DetectorRuntime:
    def __init__(self) -> None:
        self.logger = init_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
        self.status = DetectionStatus()
        # pick up TESSERACT_PATH default if present
        self.status.tesseract_path = os.environ.get("TESSERACT_PATH") or None
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()
        self._evidence = StateHysteresis()
        self._session: Optional[SessionRecorder] = None

    def start(self, title: Optional[str] = None, word: Optional[str] = None, template_path: Optional[str] = None, tesseract_path: Optional[str] = None, method: Optional[str] = None, real: Optional[bool] = None, weapon: Optional[int] = None, preview_mode: Optional[str] = None) -> None:
        with self._lock:
            if self.status.running:
                # Update parameters while running
                if title: self.status.title = title
                if word: self.status.word = word
                if template_path: self.status.template_path = template_path
                if tesseract_path: self.status.tesseract_path = tesseract_path
                if method: self.status.method = method
                if real is not None: self.status.real_inputs = bool(real)
                if weapon is not None: self.status.preferred_weapon = int(weapon)
                if preview_mode: self.status.preview_mode = preview_mode
                self.status.paused = False
                self.logger.info(
                    "Runtime updated | title=%s word=%s template=%s method=%s real=%s weapon=%s",
                    self.status.title, self.status.word, self.status.template_path, self.status.method, self.status.real_inputs, self.status.preferred_weapon,
                )
                return
            if title: self.status.title = title
            if word: self.status.word = word
            if method: self.status.method = method
            self.status.template_path = template_path
            self.status.tesseract_path = tesseract_path
            if real is not None: self.status.real_inputs = bool(real)
            if weapon is not None: self.status.preferred_weapon = int(weapon)
            if preview_mode: self.status.preview_mode = preview_mode
            self.status.running = True
            self.status.paused = False
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self.logger.info(
                "Runtime started | title=%s word=%s template=%s method=%s real=%s weapon=%s",
                self.status.title, self.status.word, self.status.template_path, self.status.method, self.status.real_inputs, self.status.preferred_weapon,
            )
            # Start session recorder
            try:
                self._session = SessionRecorder()
                sid = self._session.start({
                    "title": self.status.title,
                    "word": self.status.word,
                    "method": self.status.method,
                    "real_inputs": self.status.real_inputs,
                    "preferred_weapon": self.status.preferred_weapon,
                    "preview_mode": self.status.preview_mode,
                    "tesseract_path": self.status.tesseract_path,
                })
                self.logger.info("Session started: %s", sid)
            except Exception:
                self._session = None
            # Attempt to load attack button template if available
            self._load_attack_template()

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
            self.logger.info("Runtime stopped")

    def _run_loop(self) -> None:
        win.make_dpi_aware()
        # Configure tesseract once per loop if using OCR
        if not self.status.template_path:
            configure_tesseract(self.status.tesseract_path)
        last_log_t = 0.0
        last_found = None
        # R1 state machine variables
        state = "scan"
        self.status.state = state
        battle_present_frames = 0
        prime_deadline = 0.0
        prime_retries = 0
        attack_deadline = 0.0
        attack_retries = 0
        weapon_deadline = 0.0
        weapon_retries = 0
        battle_absent_frames = 0
        name_box: Optional[Tuple[int,int,int,int]] = None
        battle_started_at = 0.0
        # Prepare panel stability tracking
        prepare_present_frames = 0
        prepare_missing_frames = 0
        panel_rect: Optional[Tuple[int,int,int,int]] = None
        attack_seen_frames = 0
        attack_clicked = False
        weapon_try_index = 0
        last_prime_click: Optional[Tuple[int,int]] = None
        last_click_point: Optional[Tuple[int,int]] = None
        prepare_since: float = 0.0
        while not self._stop_evt.is_set():
            if self.status.paused:
                time.sleep(0.1)
                continue
            try:
                hwnd = win.find_window_exact(self.status.title)
                if not hwnd:
                    msg = {"error": f"Window not found: {self.status.title}"}
                    self._set_result(msg, frame=None)
                    now = time.time()
                    if now - last_log_t > 2.0:
                        self.logger.warning("%s", msg["error"]) 
                        last_log_t = now
                    time.sleep(0.5)
                    continue
                x, y, w, h = win.get_client_rect(hwnd)
                # Choose ROI by state
                # Always grab full frame for preview composition
                fx, fy, fw, fh = win.get_client_rect(hwnd)
                full_frame = capture.grab_rect(fx, fy, fw, fh)

                # Phase A: compute state evidence (does not drive behavior yet)
                ev_scores, ev_details, ev_rois = compute_evidence(full_frame, x, y, w, h, last_prime_click)
                stable = self._evidence.update(StateEvidence(attack=ev_scores.get("attack", 0), prepare=ev_scores.get("prepare", 0), battle=ev_scores.get("battle", 0)))
                # Persist evidence snapshot on state change
                try:
                    if self._session:
                        self._session.write_event({
                            "ts": time.time(),
                            "type": "evidence",
                            "state": state,
                            "evidence": ev_scores,
                            "stable": stable,
                        })
                except Exception:
                    pass
                # Annotate evidence ROIs on a copy for preview if in full mode
                evid_overlay = None
                if self.status.preview_mode == "full":
                    evid_overlay = full_frame.copy()
                    # attack rois in yellow, prepare in magenta, battle in green
                    for (rx1, ry1, rw1, rh1) in ev_rois.get("attack", []):
                        cv2.rectangle(evid_overlay, (rx1, ry1), (rx1 + rw1, ry1 + rh1), (0, 255, 255), 1)
                    pr = ev_rois.get("prepare", [])
                    if pr:
                        rx1, ry1, rw1, rh1 = pr[0]
                        cv2.rectangle(evid_overlay, (rx1, ry1), (rx1 + rw1, ry1 + rh1), (255, 0, 255), 1)
                    br = ev_rois.get("battle", [])
                    if br:
                        rx1, ry1, rw1, rh1 = br[0]
                        cv2.rectangle(evid_overlay, (rx1, ry1), (rx1 + rw1, ry1 + rh1), (0, 255, 0), 1)

                if state == "scan":
                    rx, ry, rw, rh = self._roi_pixels(x, y, w, h)
                    frame = capture.grab_rect(rx, ry, rw, rh)
                    boxes, best_conf = detect_word_ocr_multi(frame, target=self.status.word)
                    if self.status.preview_mode == "full":
                        annotated = full_frame.copy()
                        # Draw ROI rectangle
                        cv2.rectangle(annotated, (rx, ry), (rx + rw, ry + rh), (255, 255, 0), 2)
                        for (bx, by, bw, bh) in boxes:
                            cv2.rectangle(annotated, (rx + bx, ry + by), (rx + bx + bw, ry + by + bh), (0, 0, 255), 2)
                        # Overlay evidence summary text
                        cv2.putText(annotated, f"EV a:{ev_scores['attack']} p:{ev_scores['prepare']} b:{ev_scores['battle']} -> {stable}", (rx, max(ry-8, y+12)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,255), 1, cv2.LINE_AA)
                    else:
                        annotated = frame.copy()
                        for (bx, by, bw, bh) in boxes:
                            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 0, 255), 2)
                    ok, jpg = cv2.imencode('.jpg', annotated)
                    preview = jpg.tobytes() if ok else None
                    self._set_result({
                        "state": state,
                        "found": bool(boxes),
                        "boxes": boxes,
                        "roi": [rx, ry, rw, rh],
                        "preview_mode": self.status.preview_mode,
                        "evidence": ev_scores,
                        "evidence_state": stable,
                        "evidence_details": ev_details,
                    }, preview)
                    if boxes:
                        # Pick the largest box
                        name_box = max(boxes, key=lambda b: b[2] * b[3])
                        # Compute click under nameplate
                        nbx, nby, nbw, nbh = name_box
                        cx = rx + nbx + nbw // 2
                        cy = ry + nby + nbh + int(1.4 * nbh)
                        timeline.add(state, "click", "prime_target", click={"x": cx, "y": cy}, name_box=name_box)
                        if self.status.real_inputs:
                            win.bring_to_foreground(hwnd)
                            click_screen(cx, cy, jitter_px=4, delay_ms=25)
                        last_prime_click = (cx, cy)
                        last_click_point = (cx, cy)
                        prime_deadline = time.time() + 1.6
                        prime_retries = 0
                        state = "prime"
                        self.status.state = state
                        continue
                elif state == "prime":
                    # Dynamic Attack ROI anchored around last prime click (falls back to static region)
                    def clamp_rect(rx:int, ry:int, rw:int, rh:int) -> Tuple[int,int,int,int]:
                        rx = max(x, min(rx, x + w - 1))
                        ry = max(y, min(ry, y + h - 1))
                        rw = max(1, min(rw, x + w - rx))
                        rh = max(1, min(rh, y + h - ry))
                        return rx, ry, rw, rh

                    dyn_tried = []
                    if last_prime_click:
                        pcx, pcy = last_prime_click
                        rw_guess = max(320, int(0.30 * w))
                        rh_guess = max(180, int(0.22 * h))
                        # Right-hand guess
                        arx, ary, arw, arh = clamp_rect(pcx + 10, pcy - rh_guess // 2, rw_guess, rh_guess)
                        dyn_tried.append((arx, ary, arw, arh))
                        aframe = capture.grab_rect(arx, ary, arw, arh)
                    else:
                        arx, ary, arw, arh = (int(x + 0.52 * w), int(y + 0.16 * h), int(0.48 * w), int(0.68 * h))
                        dyn_tried.append((arx, ary, arw, arh))
                        aframe = capture.grab_rect(arx, ary, arw, arh)
                    # OCR precise (preprocessed) and tolerant union
                    aboxes_strict = detect_attack_button_boxes(aframe)
                    aboxes_tol, _ = ocr_find_words(aframe, target="attack", whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", psm=6, upscale=1.5, exact=False)
                    merged_attacks = aboxes_strict + aboxes_tol
                    if merged_attacks:
                        from bsbot.vision import detect as _vd
                        scores = [0.9]*len(aboxes_strict) + [0.7]*len(aboxes_tol)
                        keep = _vd._nms(merged_attacks, scores, iou_thresh=0.5)  # type: ignore[attr-defined]
                        merged_attacks = [merged_attacks[i] for i in keep]

                    # If nothing found and we had a prime click, try mirrored (left) ROI once
                    if not merged_attacks and last_prime_click:
                        pcx, pcy = last_prime_click
                        rw_guess = max(320, int(0.30 * w))
                        rh_guess = max(180, int(0.22 * h))
                        arx2, ary2, arw2, arh2 = clamp_rect(pcx - rw_guess - 10, pcy - rh_guess // 2, rw_guess, rh_guess)
                        try:
                            aframe2 = capture.grab_rect(arx2, ary2, arw2, arh2)
                            aboxes_strict2 = detect_attack_button_boxes(aframe2)
                            aboxes_tol2, _ = ocr_find_words(aframe2, target="attack", whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", psm=6, upscale=1.5, exact=False)
                            merged2 = aboxes_strict2 + aboxes_tol2
                            if merged2:
                                from bsbot.vision import detect as _vd
                                sc2 = [0.9]*len(aboxes_strict2) + [0.7]*len(aboxes_tol2)
                                keep2 = _vd._nms(merged2, sc2, iou_thresh=0.5)  # type: ignore[attr-defined]
                                merged_attacks = [merged2[i] for i in keep2]
                                arx, ary, arw, arh = arx2, ary2, arw2, arh2
                                aframe = aframe2
                                dyn_tried.append((arx2, ary2, arw2, arh2))
                        except Exception:
                            pass

                    # Render preview
                    if self.status.preview_mode == "full":
                        annotated = full_frame.copy()
                        # Draw all tried ROIs
                        for (tx1, ty1, tw1, th1) in dyn_tried:
                            cv2.rectangle(annotated, (tx1, ty1), (tx1 + tw1, ty1 + th1), (255, 255, 0), 2)
                        for (bx, by, bw, bh) in merged_attacks:
                            cv2.rectangle(annotated, (arx + bx, ary + by), (arx + bx + bw, ary + by + bh), (0, 255, 0), 2)
                        if last_click_point:
                            cv2.drawMarker(annotated, last_click_point, (0, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=12, thickness=2)
                        # Evidence summary
                        cv2.putText(annotated, f"EV a:{ev_scores['attack']} p:{ev_scores['prepare']} b:{ev_scores['battle']} -> {stable}", (x+8, y+18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,255), 1, cv2.LINE_AA)
                    else:
                        annotated = aframe.copy()
                        for (bx, by, bw, bh) in merged_attacks:
                            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
                    ok, jpg = cv2.imencode('.jpg', annotated)
                    preview = jpg.tobytes() if ok else None
                    self._set_result({"state": state, "attack_boxes": merged_attacks, "roi": [arx, ary, arw, arh], "evidence": ev_scores, "evidence_state": stable, "evidence_details": ev_details}, preview)

                    # Debounce: need 2 consecutive frames before click
                    if merged_attacks:
                        attack_seen_frames += 1
                    else:
                        attack_seen_frames = 0
                    if merged_attacks and attack_seen_frames >= 2:
                        bx, by, bw, bh = max(merged_attacks, key=lambda b: b[2] * b[3])
                        cx = arx + bx + bw // 2
                        cy = ary + by + bh // 2
                        timeline.add(state, "click", "attack_button", click={"x": cx, "y": cy})
                        if self.status.real_inputs:
                            win.bring_to_foreground(hwnd)
                            click_screen(cx, cy, jitter_px=2, delay_ms=20)
                        attack_deadline = time.time() + 1.6
                        attack_retries = 0
                        attack_clicked = True
                        last_click_point = (cx, cy)
                        state = "attack_panel"
                        self.status.state = state
                        continue
                    if time.time() > prime_deadline:
                        if prime_retries < 2 and name_box is not None:
                            nbx, nby, nbw, nbh = name_box
                            cx = int(x + self.status.roi[0] * w) + nbx + nbw // 2
                            cy = int(y + self.status.roi[1] * h) + nby + nbh + int(1.4 * nbh)
                            timeline.add(state, "retry", "prime_target", click={"x": cx, "y": cy}, retry=prime_retries+1)
                            if self.status.real_inputs:
                                win.bring_to_foreground(hwnd)
                                click_screen(cx, cy, jitter_px=4, delay_ms=25)
                            prime_retries += 1
                            prime_deadline = time.time() + 1.6
                            # Save crop for debugging every 3 retries
                            try:
                                if self._session and (prime_retries % 3 == 0):
                                    rel = self._session.save_crop(aframe, f"attack_roi_{int(time.time())}.jpg")
                                    self._session.write_event({"ts": time.time(), "type": "prime_timeout_crop", "path": rel, "roi": [arx, ary, arw, arh]})
                            except Exception:
                                pass
                        else:
                            timeline.add(state, "timeout", "prime")
                            state = "scan"
                            self.status.state = state
                            continue
                elif state == "attack_panel":
                    # Look for Prepare panel text
                    prx, pry, prw, prh = (int(x + 0.55 * w), int(y + 0.07 * h), int(0.43 * w), int(0.86 * h))
                    pframe = capture.grab_rect(prx, pry, prw, prh)
                    pboxes1, _ = ocr_find_words(pframe, target="prepare", whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ ", exact=False)
                    # Secondary cue: look for combinations like FOR+BATTLE or CHOOSE+START
                    token_map = ocr_find_tokens(pframe, ["choose", "attack", "for", "battle", "start"], whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ ")
                    pboxes2 = (token_map.get("choose") or []) + (token_map.get("attack") or []) + (token_map.get("for") or []) + (token_map.get("battle") or [])
                    if self.status.preview_mode == "full":
                        annotated = full_frame.copy()
                        cv2.rectangle(annotated, (prx, pry), (prx + prw, pry + prh), (255, 255, 0), 2)
                        for (bx, by, bw, bh) in (pboxes1 + pboxes2):
                            cv2.rectangle(annotated, (prx + bx, pry + by), (prx + bx + bw, pry + by + bh), (255, 0, 0), 2)
                    else:
                        annotated = pframe.copy()
                        for (bx, by, bw, bh) in (pboxes1 + pboxes2):
                            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (255, 0, 0), 2)
                    ok, jpg = cv2.imencode('.jpg', annotated)
                    preview = jpg.tobytes() if ok else None
                    self._set_result({"state": state, "prepare_boxes": pboxes1 + pboxes2, "roi": [prx, pry, prw, prh], "attack_clicked": attack_clicked, "evidence": ev_scores, "evidence_state": stable, "evidence_details": ev_details}, preview)
                    # Only accept prepare if we've actually clicked attack
                    if attack_clicked and (pboxes1 or (token_map.get("for") and token_map.get("battle")) or (token_map.get("choose") and token_map.get("start"))):
                        prepare_present_frames += 1
                        if prepare_present_frames >= 2:
                            panel_rect = (prx, pry, prw, prh)
                            timeline.add(state, "confirm", "prepare_panel")
                            try:
                                if self._session:
                                    rel = self._session.save_crop(pframe, f"prepare_roi_{int(time.time())}.jpg")
                                    self._session.write_event({"ts": time.time(), "type": "prepare_confirm", "path": rel, "roi": [prx, pry, prw, prh]})
                            except Exception:
                                pass
                            # Move to dedicated prepare state that performs the weapon click
                            weapon_try_index = 0
                            prepare_since = time.time()
                            state = "prepare"
                            self.status.state = state
                            prepare_missing_frames = 0
                            continue
                    else:
                        prepare_present_frames = 0
                    if time.time() > attack_deadline:
                        if attack_retries < 1:
                            # Click attack again — reuse center of last found box if stored; otherwise, retry prime
                            arx, ary, arw, arh = (int(x + 0.52 * w), int(y + 0.16 * h), int(0.48 * w), int(0.68 * h))
                            aframe = capture.grab_rect(arx, ary, arw, arh)
                            aboxes, _ = ocr_find_words(aframe, target="attack", whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ", psm=6, upscale=1.5, exact=False)
                            if aboxes:
                                bx, by, bw, bh = max(aboxes, key=lambda b: b[2] * b[3])
                                cx = arx + bx + bw // 2
                                cy = ary + by + bh // 2
                                timeline.add(state, "retry", "attack_button", click={"x": cx, "y": cy}, retry=attack_retries+1)
                                if self.status.real_inputs:
                                    win.bring_to_foreground(hwnd)
                                    click_screen(cx, cy, jitter_px=3, delay_ms=25)
                                attack_retries += 1
                                attack_deadline = time.time() + 1.2
                            else:
                                timeline.add(state, "timeout", "attack_not_found")
                                attack_clicked = False
                                state = "scan"
                                self.status.state = state
                        else:
                            timeline.add(state, "timeout", "attack")
                            attack_clicked = False
                            state = "scan"
                            self.status.state = state
                            continue
                elif state == "prepare":
                    # Ensure panel still present
                    if panel_rect is None:
                        state = "attack_panel"
                        self.status.state = state
                        continue
                    prx, pry, prw, prh = panel_rect
                    pframe = capture.grab_rect(prx, pry, prw, prh)
                    token_map = ocr_find_tokens(pframe, ["choose", "attack", "prepare", "first", "start"], whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ ")
                    present = (token_map.get("prepare") or (token_map.get("choose") and token_map.get("attack")) or (token_map.get("choose") and token_map.get("start")) or (token_map.get("first") and token_map.get("attack")))
                    # Be tolerant for the first ~1.2s after confirm
                    if present or (time.time() - prepare_since < 1.2):
                        prepare_missing_frames = 0
                        # Click weapon 1 now (try OCR digit first, then geometric candidates)
                        candidates: List[Tuple[int,int]] = []
                        try:
                            slots_rx, slots_ry, slots_rw, slots_rh = prx, pry + prh // 2, prw, prh // 2
                            sframe = capture.grab_rect(slots_rx, slots_ry, slots_rw, slots_rh)
                            # Try single char mode first, then word mode
                            digit_boxes, _ = ocr_find_words(sframe, target="1", whitelist="0123456789", psm=7, exact=True)
                            if digit_boxes:
                                bx, by, bw, bh = max(digit_boxes, key=lambda b: b[2] * b[3])
                                candidates.append((slots_rx + bx + bw // 2, slots_ry + by + int(2.2 * bh)))
                            else:
                                # Fallback: leftmost count marker ('xN') near bottom to infer column center
                                lm = find_leftmost_count_marker(pframe)
                                if lm:
                                    cxm, cym = lm
                                    candidates.append((cxm, cym - int(0.12 * prh)))
                        except Exception:
                            pass
                        # Geometric fallbacks for slot-1 center (two nearby centers)
                        candidates.extend([
                            (prx + int(0.160 * prw), pry + int(0.803 * prh)),
                            (prx + int(0.145 * prw), pry + int(0.795 * prh)),
                        ])
                        # Choose candidate by try index
                        cx, cy = candidates[min(weapon_try_index, len(candidates)-1)]
                        timeline.add(state, "click", "weapon_1", click={"x": cx, "y": cy}, try_index=weapon_try_index)
                        if self.status.real_inputs:
                            win.bring_to_foreground(hwnd)
                            click_screen(cx, cy, jitter_px=4, delay_ms=25)
                        last_click_point = (cx, cy)
                        weapon_deadline = time.time() + 1.5
                        weapon_retries = 0
                        state = "weapon"
                        self.status.state = state
                        continue
                    else:
                        prepare_missing_frames += 1
                        if prepare_missing_frames >= 3:
                            timeline.add(state, "timeout", "prepare_lost")
                            attack_clicked = False
                            try:
                                if self._session:
                                    rel = self._session.save_crop(pframe, f"prepare_lost_{int(time.time())}.jpg")
                                    self._session.write_event({"ts": time.time(), "type": "prepare_lost", "path": rel, "roi": [prx, pry, prw, prh]})
                            except Exception:
                                pass
                            state = "attack_panel"
                            self.status.state = state
                            continue

                elif state == "weapon":
                    # Confirm battle start by SPECIAL ATTACKS label in bottom bar
                    brx, bry, brw, brh = (int(x + 0.10 * w), int(y + 0.83 * h), int(0.80 * w), int(0.15 * h))
                    bframe = capture.grab_rect(brx, bry, brw, brh)
                    tokens = ocr_find_tokens(bframe, ["special", "attacks", "weapons"], whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ ")
                    sboxes = (tokens.get("special") or []) + (tokens.get("attacks") or [])
                    wboxes = tokens.get("weapons") or []
                    if self.status.preview_mode == "full":
                        annotated = full_frame.copy()
                        cv2.rectangle(annotated, (brx, bry), (brx + brw, bry + brh), (255, 255, 0), 2)
                        for (bx, by, bw, bh) in sboxes:
                            cv2.rectangle(annotated, (brx + bx, bry + by), (brx + bx + bw, bry + by + bh), (0, 128, 255), 2)
                        for (bx, by, bw, bh) in wboxes:
                            cv2.rectangle(annotated, (brx + bx, bry + by), (brx + bx + bw, bry + by + bh), (128, 255, 0), 2)
                    else:
                        annotated = bframe.copy()
                        for (bx, by, bw, bh) in sboxes:
                            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 128, 255), 2)
                        for (bx, by, bw, bh) in wboxes:
                            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (128, 255, 0), 2)
                    ok, jpg = cv2.imencode('.jpg', annotated)
                    preview = jpg.tobytes() if ok else None
                    self._set_result({"state": state, "special_attacks": bool(tokens.get("special")) and bool(tokens.get("attacks")), "weapons": bool(wboxes), "roi": [brx, bry, brw, brh], "evidence": ev_scores, "evidence_state": stable, "evidence_details": ev_details}, preview)
                    # Require BOTH labels and 3 consecutive frames to enter battle
                    if (tokens.get("special") and tokens.get("attacks")) and wboxes:
                        battle_present_frames += 1
                        if battle_present_frames >= 3:
                            timeline.add(state, "confirm", "battle_started")
                            battle_absent_frames = 0
                            battle_present_frames = 0
                            battle_started_at = time.time()
                            try:
                                if self._session:
                                    rel = self._session.save_crop(bframe, f"battle_start_{int(time.time())}.jpg")
                                    self._session.write_event({"ts": time.time(), "type": "battle_start", "path": rel, "roi": [brx, bry, brw, brh]})
                            except Exception:
                                pass
                            state = "battle"
                            self.status.state = state
                            continue
                    else:
                        battle_present_frames = 0
                    if time.time() > weapon_deadline:
                        if weapon_retries < 1:
                            # Retry clicking weapon center
                            if panel_rect is not None:
                                prx, pry, prw, prh = panel_rect
                                # Try next candidate center
                                weapon_try_index += 1
                                cx = prx + int(0.170 * prw) if weapon_try_index % 2 == 1 else prx + int(0.140 * prw)
                                cy = pry + int(0.80 * prh)
                                timeline.add(state, "retry", "weapon_1", click={"x": cx, "y": cy}, retry=weapon_retries+1)
                                if self.status.real_inputs:
                                    win.bring_to_foreground(hwnd)
                                    click_screen(cx, cy, jitter_px=4, delay_ms=25)
                            if self.status.real_inputs:
                                pass
                            weapon_retries += 1
                            weapon_deadline = time.time() + 1.5
                        else:
                            timeline.add(state, "timeout", "weapon")
                            state = "scan"
                            self.status.state = state
                            continue
                elif state == "battle":
                    brx, bry, brw, brh = (int(x + 0.10 * w), int(y + 0.83 * h), int(0.80 * w), int(0.15 * h))
                    bframe = capture.grab_rect(brx, bry, brw, brh)
                    tokens = ocr_find_tokens(bframe, ["special", "attacks", "weapons"], whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ ")
                    s_present = bool(tokens.get("special")) and bool(tokens.get("attacks"))
                    wboxes = tokens.get("weapons") or []
                    if self.status.preview_mode == "full":
                        annotated = full_frame.copy()
                        cv2.rectangle(annotated, (brx, bry), (brx + brw, bry + brh), (255, 255, 0), 2)
                        for (bx, by, bw, bh) in sboxes:
                            cv2.rectangle(annotated, (brx + bx, bry + by), (brx + bx + bw, bry + by + bh), (0, 128, 255), 2)
                        for (bx, by, bw, bh) in wboxes:
                            cv2.rectangle(annotated, (brx + bx, bry + by), (brx + bx + bw, bry + by + bh), (128, 255, 0), 2)
                    else:
                        annotated = bframe.copy()
                        for (bx, by, bw, bh) in sboxes:
                            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 128, 255), 2)
                        for (bx, by, bw, bh) in wboxes:
                            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (128, 255, 0), 2)
                    ok, jpg = cv2.imencode('.jpg', annotated)
                    preview = jpg.tobytes() if ok else None
                    self._set_result({"state": state, "special_attacks": s_present, "weapons": bool(wboxes), "roi": [brx, bry, brw, brh]}, preview)
                    present = bool(s_present and wboxes)
                    if present:
                        battle_absent_frames = 0
                    else:
                        battle_absent_frames += 1
                        # Exit if sentinel absent long enough or battle runs too long (>180s)
                        if battle_absent_frames >= 6 or (battle_started_at and time.time() - battle_started_at > 180):
                            timeline.add(state, "transition", "battle_over")
                            try:
                                if self._session:
                                    rel = self._session.save_crop(bframe, f"battle_end_{int(time.time())}.jpg")
                                    self._session.write_event({"ts": time.time(), "type": "battle_over", "path": rel, "roi": [brx, bry, brw, brh]})
                            except Exception:
                                pass
                            state = "scan"
                            self.status.state = state
                            continue

                # periodic info log
                now = time.time()
                if now - last_log_t > 2.0:
                    self.logger.info("state=%s", state)
                    last_log_t = now
            except Exception as e:
                # On any exception, publish the error, log it, and fall back to scan state
                self._set_result({"error": str(e)}, frame=None)
                self.logger.exception("runtime error")
                state = "scan"
                self.status.state = state
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

    # OCR-only mode: no template loading required
