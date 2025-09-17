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
from bsbot.core.config import load_profile, load_keys
from bsbot.core.session import SessionRecorder


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
        word = data.get("word") or "Wendigo"
        template = data.get("template") or None
        tess = data.get("tesseract_path") or None
        method = data.get("method") or "auto"
        real = bool(data.get("real_inputs", False))
        weapon = int(data.get("weapon", 1))
        preview_mode = (data.get("preview_mode") or "full").lower()
        rt.start(title=title, word=word, template_path=template, tesseract_path=tess, method=method, real=real, weapon=weapon, preview_mode=preview_mode)
        logger.info("api/start | title=%s word=%s template=%s method=%s real=%s weapon=%s preview=%s", title, word, template, method, real, weapon, preview_mode)
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
            "template": s.template_path,
            "method": s.method,
            # Include config values when available
            "profile": profile_config,
            "keys": keys_config,
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

    @app.get("/api/sessions")
    def api_sessions():
        from bsbot.core.session import SessionRecorder
        return jsonify({"sessions": SessionRecorder.list_sessions()})

    @app.get("/api/sessions/latest")
    def api_sessions_latest():
        from bsbot.core.session import SessionRecorder
        lst = SessionRecorder.list_sessions()
        return jsonify({"id": (lst[0] if lst else None)})

    @app.get("/api/session/<sid>/events")
    def api_session_events(sid: str):
        base = os.path.join("logs", "sessions", sid)
        path = os.path.join(base, "events.jsonl")
        if not os.path.exists(path):
            return jsonify({"events": []})
        limit = int(request.args.get("limit", 200))
        lines = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-limit:]
        except Exception:
            lines = []
        return jsonify({"events": [json.loads(l) for l in lines if l.strip()]})

    @app.get("/api/session/<sid>/files")
    def api_session_files(sid: str):
        base = os.path.join("logs", "sessions", sid, "crops")
        out = []
        if os.path.isdir(base):
            for root, _, files in os.walk(base):
                for fn in files:
                    rel = os.path.relpath(os.path.join(root, fn), os.path.join("logs", "sessions", sid))
                    out.append(rel.replace("\\", "/"))
        out.sort()
        return jsonify({"files": out})

    @app.get("/api/session/<sid>/file")
    def api_session_file(sid: str):
        rel = request.args.get("path", "")
        base = os.path.abspath(os.path.join("logs", "sessions", sid))
        full = os.path.abspath(os.path.join(base, rel))
        if not full.startswith(base):
            return ("bad path", 400)
        if not os.path.exists(full):
            return ("not found", 404)
        return send_file(full)

    @app.get("/api/timeline")
    def api_timeline():
        from bsbot.core.timeline import timeline
        n = int(request.args.get("n", 50))
        return jsonify({"events": timeline.last(n)})

    return app


def _toggle_pause(rt: DetectorRuntime, logger: logging.Logger):
    s = rt.snapshot()
    if s.running and not s.paused:
        rt.pause()
        logger.info("hotkey: pause")
    else:
        rt.start(title=s.title, word=s.word, template_path=s.template_path, tesseract_path=s.tesseract_path)
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
