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

    candidates: List[Tuple[int, int, int, int]] = []
    candidate_scores: List[float] = []

    def _collect(res: np.ndarray, tpl_shape: Tuple[int, int]) -> None:
        if res is None:
            return
        ys, xs = np.where(res >= threshold)
        h, w = tpl_shape
        for y, x in zip(ys, xs):
            candidates.append((int(x), int(y), int(w), int(h)))
            candidate_scores.append(float(res[y, x]))

    # Raw grayscale correlation
    res_gray = cv2.matchTemplate(gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
    _collect(res_gray, tpl_gray.shape[:2])

    # Edge-based correlation (helps with stronger outline matches)
    edges = cv2.Canny(gray, 80, 160)
    tpl_edges = cv2.Canny(tpl_gray, 80, 160)
    res_edges = cv2.matchTemplate(edges, tpl_edges, cv2.TM_CCOEFF_NORMED)
    _collect(res_edges, tpl_edges.shape[:2])

    if not candidates:
        return [], []

    keep = _nms(candidates, candidate_scores, iou_thresh=0.5)
    boxes = [candidates[i] for i in keep][:max_instances]
    scores = [candidate_scores[i] for i in keep][:max_instances]
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
