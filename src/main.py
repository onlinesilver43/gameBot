import argparse
import os
import sys
from typing import Tuple

import cv2

from . import window as win
from . import capture
from .detect import detect_word_ocr, detect_with_template, configure_tesseract
from .template_tools import extract_red_word_template, save_template


def _draw_bbox(img, bbox: Tuple[int, int, int, int], color=(0, 0, 255)):
    x, y, w, h = bbox
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)


def test_screenshot(path: str, word: str = "Wendigo", tesseract_path: str | None = None, template_out: str | None = None) -> int:
    if not os.path.exists(path):
        print(f"Screenshot not found: {path}")
        return 2
    configure_tesseract(tesseract_path)
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    det = detect_word_ocr(bgr, target=word)
    print({"found": det.found, "method": det.method, "confidence": det.confidence, "bbox": det.bbox})
    if det.found and det.bbox:
        _draw_bbox(bgr, det.bbox, (0, 0, 255))
        out = os.path.splitext(path)[0] + ".detected.png"
        cv2.imwrite(out, bgr)
        print(f"Annotated result written to {out}")
        if template_out:
            # Auto-crop a template from this screenshot via heuristic red mask
            tr = extract_red_word_template(cv2.imread(path))
            if tr.ok and tr.image is not None:
                save_template(tr.image, template_out)
                print(f"Saved template to {template_out}")
            else:
                print(f"Template extraction failed: {tr.reason}")
        return 0
    return 1


def test_window_roi(title: str = "Brighter Shores", word: str = "Wendigo", tesseract_path: str | None = None, template_path: str | None = None) -> int:
    win.make_dpi_aware()
    hwnd = win.find_window_exact(title)
    if not hwnd:
        print(f"Window not found: {title}")
        return 2
    x, y, w, h = win.get_client_rect(hwnd)
    # Central ROI where nameplates usually appear
    rx = int(x + 0.2 * w)
    ry = int(y + 0.25 * h)
    rw = int(0.6 * w)
    rh = int(0.5 * h)
    frame = capture.grab_rect(rx, ry, rw, rh)
    if template_path and os.path.exists(template_path):
        tpl = cv2.imread(template_path, cv2.IMREAD_COLOR)
        det = detect_with_template(frame, tpl)
    else:
        configure_tesseract(tesseract_path)
        det = detect_word_ocr(frame, target=word)
    print({"found": det.found, "method": det.method, "confidence": det.confidence, "bbox": det.bbox})
    if det.found and det.bbox:
        _draw_bbox(frame, det.bbox, (0, 0, 255))
        cv2.imwrite("window_roi.detected.png", frame)
        print("Annotated ROI saved as window_roi.detected.png")
        return 0
    else:
        cv2.imwrite("window_roi.png", frame)
        print("ROI saved as window_roi.png for debugging")
        return 1


def main():
    ap = argparse.ArgumentParser(description="Detection test utilities")
    ap.add_argument("--test-screenshot", dest="screenshot", help="Path to screenshot image")
    ap.add_argument("--test-window", action="store_true", help="Capture current window ROI and test OCR")
    ap.add_argument("--title", default="Brighter Shores", help="Exact window title")
    ap.add_argument("--word", default="Wendigo", help="Word to detect")
    ap.add_argument("--tesseract-path", dest="tess", default=None, help="Explicit path to tesseract.exe if not on PATH")
    ap.add_argument("--template", dest="template", default=None, help="Use template image instead of OCR if provided")
    ap.add_argument("--save-template-from", dest="tmpl_from", default=None, help="Extract a red-word template from a screenshot and save to --template path")
    args = ap.parse_args()

    if args.screenshot:
        sys.exit(test_screenshot(args.screenshot, args.word, args.tess, args.template))
    if args.test_window:
        sys.exit(test_window_roi(args.title, args.word, args.tess, args.template))
    if args.tmpl_from and args.template:
        img = cv2.imread(args.tmpl_from, cv2.IMREAD_COLOR)
        if img is None:
            print(f"Could not read screenshot: {args.tmpl_from}")
            return 2
        tr = extract_red_word_template(img)
        if tr.ok and tr.image is not None:
            save_template(tr.image, args.template)
            print(f"Saved template to {args.template}")
            return 0
        else:
            print(f"Template extraction failed: {tr.reason}")
            return 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
