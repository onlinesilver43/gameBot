from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import cv2

from bsbot.vision.detect import ocr_find_tokens


Rect = Tuple[int, int, int, int]


def clamp_rect(x: int, y: int, w: int, h: int, rx: int, ry: int, rw: int, rh: int) -> Rect:
    rx = max(x, min(rx, x + w - 1))
    ry = max(y, min(ry, y + h - 1))
    rw = max(1, min(rw, x + w - rx))
    rh = max(1, min(rh, y + h - ry))
    return rx, ry, rw, rh


def compute_rois(x: int, y: int, w: int, h: int, last_prime_click: Optional[Tuple[int, int]]) -> Dict[str, List[Rect]]:
    rois: Dict[str, List[Rect]] = {"attack": [], "prepare": [], "battle": []}
    # Prepare panel (right third)
    rois["prepare"].append((int(x + 0.55 * w), int(y + 0.07 * h), int(0.43 * w), int(0.86 * h)))
    # Battle HUD (bottom band)
    rois["battle"].append((int(x + 0.10 * w), int(y + 0.83 * h), int(0.80 * w), int(0.15 * h)))
    # Attack overlay: dynamic right/left near last_prime_click; fallback wide band
    if last_prime_click:
        pcx, pcy = last_prime_click
        rw_guess = max(320, int(0.30 * w))
        rh_guess = max(180, int(0.22 * h))
        rois["attack"].append(clamp_rect(x, y, w, h, pcx + 10, pcy - rh_guess // 2, rw_guess, rh_guess))
        rois["attack"].append(clamp_rect(x, y, w, h, pcx - rw_guess - 10, pcy - rh_guess // 2, rw_guess, rh_guess))
    rois["attack"].append((int(x + 0.52 * w), int(y + 0.16 * h), int(0.48 * w), int(0.68 * h)))
    return rois


def tokens_in_roi(frame, rect: Rect, tokens: List[str], whitelist: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ") -> Dict[str, bool]:
    rx, ry, rw, rh = rect
    crop = frame[ry:ry + rh, rx:rx + rw]
    found_map = {t.lower(): False for t in tokens}
    if rw <= 1 or rh <= 1:
        return found_map
    try:
        m = ocr_find_tokens(crop, tokens, whitelist=whitelist)
        for t, boxes in m.items():
            found_map[t] = bool(boxes)
    except Exception:
        pass
    return found_map


def compute_evidence(full_frame, x: int, y: int, w: int, h: int, last_prime_click: Optional[Tuple[int, int]]):
    """Return (evidence_scores, evidence_details, rois) for Attack/Prepare/Battle.

    evidence_scores: dict with integer scores
    evidence_details: tokens present per ROI
    rois: rectangles used per state
    """
    rois = compute_rois(x, y, w, h, last_prime_click)
    ev = {"attack": 0, "prepare": 0, "battle": 0}
    det: Dict[str, Dict[str, bool]] = {"attack": {}, "prepare": {}, "battle": {}}

    # Attack: require both 'attack' and 'info' in any attack ROI
    for r in rois["attack"]:
        att = tokens_in_roi(full_frame, r, ["ATTACK", "INFO"], whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ ")
        if att.get("attack") and att.get("info"):
            ev["attack"] = 2
            det["attack"] = {"attack": True, "info": True}
            break

    # Prepare: need any 2 groups
    rprep = rois["prepare"][0]
    group1 = tokens_in_roi(full_frame, rprep, ["PREPARE", "FOR", "BATTLE"]).copy()
    g1 = group1.get("prepare") or (group1.get("for") and group1.get("battle"))
    group2 = tokens_in_roi(full_frame, rprep, ["CHOOSE", "FIRST", "ATTACK", "START"]).copy()
    g2 = (group2.get("choose") and group2.get("start")) or (group2.get("first") and group2.get("attack"))
    # Optional third cue: VS text in mid panel (very strong in screenshots)
    g3 = tokens_in_roi(full_frame, rprep, ["VS"]).get("vs", False)
    count = int(bool(g1)) + int(bool(g2)) + int(bool(g3))
    if count >= 2:
        ev["prepare"] = count
        det["prepare"] = {"group1": bool(g1), "group2": bool(g2), "vs": bool(g3)}

    # Battle: need any 2 groups in bottom HUD
    rbat = rois["battle"][0]
    bat1 = tokens_in_roi(full_frame, rbat, ["SPECIAL", "ATTACKS"])  # both
    bat2 = tokens_in_roi(full_frame, rbat, ["WEAPONS"])  # one
    bat3 = tokens_in_roi(full_frame, rbat, ["POTIONS"])  # one
    score = 0
    if bat1.get("special") and bat1.get("attacks"):
        score += 1
    if bat2.get("weapons"):
        score += 1
    if bat3.get("potions"):
        score += 1
    if score >= 2:
        ev["battle"] = score
        det["battle"] = {"special_attacks": bat1.get("special") and bat1.get("attacks"), "weapons": bat2.get("weapons"), "potions": bat3.get("potions")}

    return ev, det, rois

