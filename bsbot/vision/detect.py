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
    # Ensure tesseract is configured; no-op if already set
    configure_tesseract()
    mask = _red_mask(bgr)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    masked = cv2.bitwise_and(gray, gray, mask=mask)
    # Slight upscale helps OCR on small UI fonts
    scale = 1.5
    resized = cv2.resize(masked, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
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
        # Safe conf extraction
        conf_list = data.get("conf", [])
        conf_str = conf_list[i] if i < len(conf_list) else "0"
        try:
            conf_val = float(conf_str)
        except Exception:
            conf_val = 0.0
        # Some tesseract builds use -1 for non-words
        if conf_val < 0:
            conf_val = 0.0

        # Safe bbox extraction
        lefts = data.get("left", [])
        tops = data.get("top", [])
        widths = data.get("width", [])
        heights = data.get("height", [])
        if i >= len(lefts) or i >= len(tops) or i >= len(widths) or i >= len(heights):
            continue
        x = int(lefts[i] / scale)
        y = int(tops[i] / scale)
        w = int(widths[i] / scale)
        h = int(heights[i] / scale)

        if text == target.lower():
            return Detection(True, (x, y, w, h), conf_val / 100.0, "ocr")
        # Allow near match: contains or high overlap with target substring
        if target.lower() in text:
            best_det = Detection(True, (x, y, w, h), conf_val / 100.0, "ocr_partial")
    return best_det


def detect_word_ocr_multi(bgr: np.ndarray, target: str = "wendigo") -> Tuple[List[Tuple[int,int,int,int]], float]:
    """Return filtered boxes that match the target word via OCR with deduplication."""
    mask = _red_mask(bgr)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    masked = cv2.bitwise_and(gray, gray, mask=mask)
    scale = 1.5
    resized = cv2.resize(masked, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    cfg = "--psm 6 -l eng -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    raw_boxes: List[Tuple[int,int,int,int]] = []
    scores: List[float] = []

    try:
        data = pytesseract.image_to_data(resized, config=cfg, output_type=pytesseract.Output.DICT)
    except Exception:
        return [], 0.0

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

        # Apply size and aspect ratio filters to reduce noise
        if not _is_valid_text_box(w, h):
            continue

        if text == target.lower() or target.lower() in text:
            raw_boxes.append((x, y, w, h))
            scores.append(conf_val / 100.0)

    # Apply NMS to remove overlapping detections
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


def detect_template_pyramid(
    bgr: np.ndarray,
    template_bgr: np.ndarray,
    scales: List[float],
    threshold: float = 0.7,
) -> Tuple[List[Tuple[int, int, int, int]], List[float]]:
    """Template match across multiple scales; returns merged boxes + scores (after NMS)."""
    all_boxes: List[Tuple[int, int, int, int]] = []
    all_scores: List[float] = []
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    for s in scales:
        if s == 1.0:
            tpl = template_bgr
        else:
            tpl = cv2.resize(template_bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC)
        tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
        tpl_edges = cv2.Canny(tpl_gray, 80, 160)
        if edges.shape[0] < tpl_edges.shape[0] or edges.shape[1] < tpl_edges.shape[1]:
            continue
        res = cv2.matchTemplate(edges, tpl_edges, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= threshold)
        h, w = tpl_edges.shape[:2]
        for y, x in zip(ys, xs):
            all_boxes.append((int(x), int(y), int(w), int(h)))
            all_scores.append(float(res[y, x]))

    if not all_boxes:
        return [], []
    keep = _nms(all_boxes, all_scores, iou_thresh=0.5)
    boxes = [all_boxes[i] for i in keep]
    scores = [all_scores[i] for i in keep]
    return boxes, scores


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


def detect_attack_button_boxes(bgr: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Find 'Attack' word boxes in the right-side overlay using OCR with strong preprocessing.

    This routine is tuned for the white 'Attack' text on a red rounded button.
    """
    # 1) Increase contrast with CLAHE
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    except Exception:
        pass
    # 2) Otsu threshold to make text crisp
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # 3) Small dilation to connect strokes
    th = cv2.medianBlur(th, 3)

    cfg = "--psm 7 -l eng -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    try:
        data = pytesseract.image_to_data(th, config=cfg, output_type=pytesseract.Output.DICT)
    except Exception:
        return []
    boxes: List[Tuple[int, int, int, int]] = []
    n = len(data.get("text", []))
    for i in range(n):
        t = (data["text"][i] or "").strip().lower()
        if t != "attack":
            continue
        lefts = data.get("left", [])
        tops = data.get("top", [])
        widths = data.get("width", [])
        heights = data.get("height", [])
        if i >= len(lefts) or i >= len(tops) or i >= len(widths) or i >= len(heights):
            continue
        x, y, w, h = int(lefts[i]), int(tops[i]), int(widths[i]), int(heights[i])
        # Filter tiny boxes
        if w < 12 or h < 10:
            continue
        boxes.append((x, y, w, h))
    return boxes


def find_leftmost_count_marker(bgr: np.ndarray) -> Optional[Tuple[int, int]]:
    """Find the leftmost 'xN' style count marker near the bottom of the prepare panel.

    Returns center (cx, cy) in ROI coordinates, or None.
    OCR-only heuristic: looks for tokens composed of x/X/0123456789 in the lower 40% of the ROI.
    """
    h, w = bgr.shape[:2]
    roi_y = int(0.55 * h)
    crop = bgr[roi_y:h, :]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    except Exception:
        pass
    cfg = "--psm 6 -l eng -c tessedit_char_whitelist=0123456789xX"
    try:
        data = pytesseract.image_to_data(gray, config=cfg, output_type=pytesseract.Output.DICT)
    except Exception:
        return None
    n = len(data.get("text", []))
    best_x = None
    best_center = None
    for i in range(n):
        t = (data["text"][i] or "").strip()
        if not t:
            continue
        # Keep short tokens likely to be 'x' or small numbers
        if len(t) > 3:
            continue
        lx = int(data.get("left", [0])[i])
        ly = int(data.get("top", [0])[i])
        ww = int(data.get("width", [0])[i])
        hh = int(data.get("height", [0])[i])
        if ww < 8 or hh < 10:
            continue
        cx = lx + ww // 2
        cy = roi_y + ly + hh // 2
        if best_x is None or cx < best_x:
            best_x = cx
            best_center = (cx, cy)
    return best_center


def ocr_find_words(
    bgr: np.ndarray,
    target: str,
    whitelist: Optional[str] = None,
    psm: int = 6,
    upscale: float = 1.5,
    exact: bool = True,
) -> Tuple[List[Tuple[int, int, int, int]], float]:
    """Word finder in a BGR image.

    - exact=True: match only exact token equality with `target` (case-insensitive)
    - exact=False: substring allowed (use sparingly)
    Returns (boxes, best_conf). Boxes are (x,y,w,h) in the input image coordinates.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if upscale != 1.0:
        gray = cv2.resize(gray, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    cfg = f"--psm {psm} -l eng"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    try:
        data = pytesseract.image_to_data(gray, config=cfg, output_type=pytesseract.Output.DICT)
    except Exception:
        return [], 0.0
    n = len(data.get("text", []))
    boxes: List[Tuple[int, int, int, int]] = []
    scores: List[float] = []
    tgt = target.lower()
    for i in range(n):
        text = (data["text"][i] or "").strip().lower()
        if not text:
            continue
        lefts = data.get("left", [])
        tops = data.get("top", [])
        widths = data.get("width", [])
        heights = data.get("height", [])
        if i >= len(lefts) or i >= len(tops) or i >= len(widths) or i >= len(heights):
            continue
        x = int(lefts[i] / upscale)
        y = int(tops[i] / upscale)
        w = int(widths[i] / upscale)
        h = int(heights[i] / upscale)
        conf_list = data.get("conf", [])
        conf_str = conf_list[i] if i < len(conf_list) else "0"
        try:
            conf = float(conf_str)
        except Exception:
            conf = 0.0
        if conf < 0:
            conf = 0.0
        if (text == tgt) if exact else (tgt in text or text in tgt):
            boxes.append((x, y, w, h))
            scores.append(conf / 100.0)
    if not boxes:
        return [], 0.0
    keep = _nms(boxes, scores, 0.5)
    boxes = [boxes[i] for i in keep]
    scores = [scores[i] for i in keep]
    best = max(scores) if scores else 0.0
    return boxes, best


def ocr_find_tokens(
    bgr: np.ndarray,
    tokens: List[str],
    whitelist: Optional[str] = None,
    psm: int = 6,
    upscale: float = 1.5,
) -> dict[str, List[Tuple[int, int, int, int]]]:
    """Find multiple exact tokens in one OCR pass, return mapping token->boxes."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if upscale != 1.0:
        gray = cv2.resize(gray, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    cfg = f"--psm {psm} -l eng"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    try:
        data = pytesseract.image_to_data(gray, config=cfg, output_type=pytesseract.Output.DICT)
    except Exception:
        return {t.lower(): [] for t in tokens}
    want = {t.lower(): [] for t in tokens}
    n = len(data.get("text", []))
    for i in range(n):
        text = (data["text"][i] or "").strip().lower()
        if not text:
            continue
        lefts = data.get("left", [])
        tops = data.get("top", [])
        widths = data.get("width", [])
        heights = data.get("height", [])
        if i >= len(lefts) or i >= len(tops) or i >= len(widths) or i >= len(heights):
            continue
        x = int(lefts[i] / upscale)
        y = int(tops[i] / upscale)
        w = int(widths[i] / upscale)
        h = int(heights[i] / upscale)
        if text in want:
            want[text].append((x, y, w, h))
    return want
