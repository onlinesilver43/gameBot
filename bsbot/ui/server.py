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
            "template": s.template_path,
            "method": s.method,
            "click_mode": s.click_mode,
            "skill": s.skill,
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
