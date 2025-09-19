from __future__ import annotations

import io
import os
from typing import Any, Dict

from flask import Flask, send_file, request, jsonify, Response, render_template
import logging
import traceback

from bsbot.runtime.service import DetectorRuntime
from bsbot.ui.hotkeys import HotkeyManager
from bsbot.core.logging import init_logging
from bsbot.core.config import load_profile, load_keys, list_monster_profiles, list_interface_profiles


def create_app() -> Flask:
    # Templates are now in the same directory as this file
    app = Flask(__name__, static_folder=None, template_folder='templates')
    logger = init_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
    rt = DetectorRuntime()
    # register global hotkeys: Ctrl+Alt+P (pause/resume), Ctrl+Alt+O (kill)
    hk = HotkeyManager(
        on_pause_toggle=lambda: (_toggle_pause(rt, logger)),
        on_kill=lambda: (_kill_process(logger)),
    )
    hk.start()

    @app.get("/")
    def index():
        return render_template('index.html')

    @app.post("/api/start")
    def api_start():
        data: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
        title = data.get("title") or "Brighter Shores"
        word = data.get("word")
        template = data.get("template") if "template" in data else None
        tess = data.get("tesseract_path") if "tesseract_path" in data else None
        method = data.get("method") or "auto"
        click_mode = data.get("click_mode") or "dry_run"
        prefix_word = data.get("prefix_word") if "prefix_word" in data else None
        skill = data.get("skill") or None
        monster_id = data.get("monster_id") or None
        interface_id = data.get("interface_id") or None
        roi = data.get("roi") or None
        if isinstance(roi, list) and len(roi) == 4:
            try:
                roi = tuple(float(v) for v in roi)  # type: ignore
            except Exception:
                roi = None
        else:
            roi = None
        rt.start(
            title=title,
            prefix_word=prefix_word,
            template_path=template,
            tesseract_path=tess,
            method=method,
            roi=roi,
            click_mode=click_mode,
            skill=skill,
            monster_id=monster_id,
            interface_id=interface_id,
        )
        logger.info(
            "api/start | title=%s monster=%s interface=%s method=%s click_mode=%s skill=%s",
            title,
            monster_id or rt.status.monster_id,
            interface_id or rt.status.interface_id,
            method,
            click_mode,
            skill or rt.status.skill,
        )
        return jsonify({"ok": True})

    @app.post("/api/pause")
    def api_pause():
        rt.pause()
        logger.info("api/pause")
        return jsonify({"ok": True})

    @app.post("/api/stop")
    def api_stop():
        rt.stop()
        logger.info("api/stop")
        return jsonify({"ok": True})

    @app.get("/api/status")
    def api_status():
        s = rt.snapshot()

        # Load config values (will be empty dict if config files don't exist)
        try:
            profile_config = load_profile()
            keys_config = load_keys()
        except Exception:
            profile_config = {}
            keys_config = {}

        out = {
            "running": s.running,
            "paused": s.paused,
            "last_result": s.last_result,
            "title": s.title,
            "word": s.word,
            "prefix_word": s.prefix_word,
            "monster_id": s.monster_id,
            "interface_id": s.interface_id,
            "phase": getattr(s, "phase", None),
            "template": s.template_path,
            "template_source": getattr(s, "template_source", None),
            "method": s.method,
            "click_mode": s.click_mode,
            "skill": s.skill,
            "roi": getattr(s, "roi", None),
            "roi_px": getattr(s, "roi_px", None),
            "roi_reference_size": getattr(s, "roi_reference_size", None),
            "compass": {
                "enabled": getattr(s, "compass_auto_align", False),
                "angle": getattr(s, "compass_angle_deg", None),
                "last_aligned": getattr(s, "compass_last_aligned", None),
                "roi": getattr(s, "compass_roi", None),
            },
            "world_tile": getattr(s, "world_tile", None),
            "minimap": {
                "toggle_key": getattr(s, "minimap_toggle_key", None),
                "last_anchor": getattr(s, "minimap_last_anchor", None),
                "anchor_interval": getattr(s, "minimap_anchor_interval_s", None),
                "roi": getattr(s, "minimap_roi", None),
            },
            "interactables": getattr(s, "interactables", []),
            "calibration": getattr(s, "calibration", {}),
            # Include config values when available
            "profile": profile_config,
            "keys": keys_config,
            "monsters": list_monster_profiles(),
            "interfaces": list_interface_profiles(),
        }
        return jsonify(out)


    @app.get("/api/preview.jpg")
    def api_preview():
        s = rt.snapshot()
        if not s.last_frame:
            return ("", 204)
        return send_file(io.BytesIO(s.last_frame), mimetype="image/jpeg", as_attachment=False, download_name="preview.jpg")

    @app.get("/api/logs/tail")
    def api_logs_tail():
        n = int(request.args.get("n", 200))
        log_dir = os.environ.get("LOG_DIR", "logs")
        path = os.path.join(log_dir, "app.log")
        if not os.path.exists(path):
            return ("", 204)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-n:]
            return Response("".join(lines), mimetype="text/plain")
        except Exception:
            return Response(traceback.format_exc(), mimetype="text/plain", status=500)

    @app.get("/api/diag")
    def api_diag():
        import cv2, numpy, mss, flask
        try:
            import pytesseract
            tver = str(pytesseract.get_tesseract_version())
        except Exception as e:
            tver = f"not available: {e}"
        return jsonify({
            "cv2": cv2.__version__,
            "numpy": numpy.__version__,
            "mss": mss.__version__,
            "flask": flask.__version__,
            "tesseract": tver,
        })

    @app.get("/api/timeline")
    def api_timeline():
        try:
            return jsonify(rt.get_timeline())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.get("/api/interactables/records")
    def api_interactable_records():
        try:
            return jsonify(rt.list_interactable_records())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/interactables/record")
    def api_interactable_record():
        payload = request.get_json(force=True, silent=True) or {}
        interactable_id = payload.get("interactable_id")
        roi_rel = payload.get("roi_rel")
        notes = payload.get("notes")
        if not interactable_id or not isinstance(roi_rel, (list, tuple)) or len(roi_rel) != 2:
            return jsonify({"error": "interactable_id and roi_rel[2] required"}), 400

        snapshot = rt.snapshot()
        roi_rect = None
        last_result = snapshot.last_result or {}
        if isinstance(last_result, dict) and isinstance(last_result.get("roi"), list) and len(last_result["roi"]) == 4:
            roi_rect = last_result["roi"]
        elif isinstance(snapshot.roi, (list, tuple)) and len(snapshot.roi) == 4:
            # ROI stored as relative fractions; without window rect we cannot project accurately
            return jsonify({"error": "ROI absolute coordinates unavailable"}), 409
        if not roi_rect:
            return jsonify({"error": "ROI data unavailable"}), 409

        rx, ry, rw, rh = roi_rect
        try:
            fx = float(roi_rel[0])
            fy = float(roi_rel[1])
        except (TypeError, ValueError):
            return jsonify({"error": "roi_rel must be numeric"}), 400
        if rw <= 0 or rh <= 0:
            return jsonify({"error": "ROI has zero size"}), 409

        roi_x = int(round(fx * rw))
        roi_y = int(round(fy * rh))
        screen_x = int(round(rx + roi_x))
        screen_y = int(round(ry + roi_y))

        record = rt.record_interactable_position(
            str(interactable_id),
            roi_rel=(fx, fy),
            roi_xy=(roi_x, roi_y),
            screen_xy=(screen_x, screen_y),
            notes=notes if isinstance(notes, str) and notes.strip() else None,
        )
        return jsonify(record)

    @app.post("/api/interactables/save")
    def api_interactable_save():
        payload = request.get_json(force=True, silent=True) or {}
        interactable_id = payload.get("interactable_id")
        coords = payload.get("coords")
        roi_xy = payload.get("roi_xy")
        screen_xy = payload.get("screen_xy")
        element_index = payload.get("element_index", 0)

        if not interactable_id or not isinstance(coords, (list, tuple)) or len(coords) != 2:
            return jsonify({"error": "interactable_id and coords[2] required"}), 400

        try:
            fx = float(coords[0])
            fy = float(coords[1])
        except (TypeError, ValueError):
            return jsonify({"error": "coords must be numeric"}), 400

        roi_tuple = None
        if isinstance(roi_xy, (list, tuple)) and len(roi_xy) == 2:
            roi_tuple = (int(roi_xy[0]), int(roi_xy[1]))
        screen_tuple = None
        if isinstance(screen_xy, (list, tuple)) and len(screen_xy) == 2:
            screen_tuple = (int(screen_xy[0]), int(screen_xy[1]))

        try:
            profile = rt.save_interactable_profile(
                str(interactable_id),
                coords=(fx, fy),
                roi_xy=roi_tuple,
                screen_xy=screen_tuple,
                element_index=int(element_index) if isinstance(element_index, int) or str(element_index).isdigit() else 0,
            )
        except FileNotFoundError:
            return jsonify({"error": "profile not found"}), 404
        except Exception as exc:
            logger.exception("interactable save failed")
            return jsonify({"error": str(exc)}), 500

        return jsonify({"ok": True, "profile": profile})

    return app


def _toggle_pause(rt: DetectorRuntime, logger: logging.Logger):
    s = rt.snapshot()
    if s.running and not s.paused:
        rt.pause()
        logger.info("hotkey: pause")
    else:
        rt.start(
            title=s.title,
            word=s.word,
            prefix_word=s.prefix_word,
            template_path=s.template_path,
            tesseract_path=s.tesseract_path,
            method=s.method,
            roi=s.roi,
            click_mode=s.click_mode,
            skill=s.skill,
            monster_id=s.monster_id,
            interface_id=s.interface_id,
        )
        logger.info("hotkey: resume/start")


def _kill_process(logger: logging.Logger):
    logger.critical("hotkey: kill process")
    os._exit(0)




def main() -> None:
    app = create_app()
    port = int(os.environ.get("PORT", "8083"))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
