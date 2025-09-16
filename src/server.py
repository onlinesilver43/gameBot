from __future__ import annotations

import io
import os
from typing import Any, Dict

from flask import Flask, send_file, request, jsonify, Response
import logging
import traceback

from .runtime import DetectorRuntime
from .hotkeys import HotkeyManager
from .logging_setup import init_logging


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    logger = init_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
    rt = DetectorRuntime()
    # register global hotkeys: Ctrl+Alt+P (pause/resume), Ctrl+Alt+O (kill)
    hk = HotkeyManager(
        on_pause_toggle=lambda: (_toggle_pause(rt, logger)),
        on_kill=lambda: (_kill_process(logger)),
    )
    hk.start()

    @app.get("/")
    def index() -> Response:
        html = _INDEX_HTML
        return Response(html, mimetype="text/html")

    @app.post("/api/start")
    def api_start():
        data: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
        title = data.get("title") or "Brighter Shores"
        word = data.get("word") or "Wendigo"
        template = data.get("template") or None
        tess = data.get("tesseract_path") or None
        rt.start(title=title, word=word, template_path=template, tesseract_path=tess)
        logger.info("api/start | title=%s word=%s template=%s", title, word, template)
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
        out = {
            "running": s.running,
            "paused": s.paused,
            "last_result": s.last_result,
            "title": s.title,
            "word": s.word,
            "template": s.template_path,
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


_INDEX_HTML = r"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Brighter Shores Bot</title>
    <style>
      body { font-family: system-ui, Arial, sans-serif; margin: 20px; color: #111; }
      .row { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
      input[type=text] { padding: 6px 8px; min-width: 280px; }
      button { padding: 8px 12px; cursor: pointer; }
      #status { margin-top: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: #f6f8fa; padding: 8px; border-radius: 6px; }
      #preview { width: 100%; max-width: 960px; border: 1px solid #ddd; border-radius: 6px; }
      .hdr { font-weight: 700; margin: 12px 0 6px; }
      #logs { white-space: pre-wrap; background: #0b1020; color: #e8f0ff; padding: 8px; border-radius: 6px; font-family: ui-monospace, monospace; height: 260px; overflow: auto; }
    </style>
  </head>
  <body>
    <h2>Brighter Shores Bot</h2>

    <div class="row">
      <label>Window Title</label>
      <input id="title" type="text" value="Brighter Shores" />
    </div>
    <div class="row">
      <label>Word</label>
      <input id="word" type="text" value="Wendigo" />
    </div>
    <div class="row">
      <label>Template (optional)</label>
      <input id="template" type="text" placeholder="assets\\templates\\wendigo.png" />
    </div>
    <div class="row">
      <label>Tesseract Path (optional)</label>
      <input id="tess" type="text" placeholder="C:\\Program Files\\Tesseract-OCR\\tesseract.exe" />
    </div>
    <div class="row">
      <button id="start">Start</button>
      <button id="pause">Pause</button>
      <button id="stop">Stop</button>
    </div>

    <div class="hdr">Status</div>
    <pre id="status">{}</pre>

    <div class="hdr">Preview</div>
    <img id="preview" alt="live preview" />

    <div class="hdr">Logs (tail)</div>
    <div id="logs"></div>

    <script>
      const $ = (id) => document.getElementById(id);
      const start = async () => {
        const body = {
          title: $("title").value,
          word: $("word").value,
          template: $("template").value || null,
          tesseract_path: $("tess").value || null,
        };
        await fetch('/api/start', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      };
      const pause = () => fetch('/api/pause', { method: 'POST'});
      const stop = () => fetch('/api/stop', { method: 'POST'});

      $("start").onclick = start;
      $("pause").onclick = () => pause();
      $("stop").onclick = () => stop();

      async function poll() {
        try {
          const r = await fetch('/api/status');
          const j = await r.json();
          const nice = { ...j };
          if (nice.last_result && nice.last_result.boxes) {
            nice.last_result.count = nice.last_result.count || nice.last_result.boxes.length;
          }
          $("status").textContent = JSON.stringify(nice, null, 2);
          // Bust cache
          $("preview").src = '/api/preview.jpg?ts=' + Date.now();
        } catch (e) {
          // ignore
        }
        try {
          const lr = await fetch('/api/logs/tail?n=200');
          if (lr.status === 200) {
            const text = await lr.text();
            $("logs").textContent = text;
            $("logs").scrollTop = $("logs").scrollHeight;
          }
        } catch (e) {}
      }
      setInterval(poll, 500);
      poll();
    </script>
  </body>
  </html>
"""


def main() -> None:
    app = create_app()
    port = int(os.environ.get("PORT", "8083"))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
