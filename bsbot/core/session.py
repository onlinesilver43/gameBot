from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

import cv2  # type: ignore
import numpy as np  # type: ignore


def _now_id() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


class SessionRecorder:
    """Simple JSONL + crops recorder for a runtime session.

    Directory layout:
      logs/sessions/<id>/
        meta.json
        events.jsonl
        crops/*.jpg
    """

    def __init__(self, base_dir: str = "logs/sessions") -> None:
        self.base_dir = base_dir
        self.session_id: Optional[str] = None
        self.dir: Optional[str] = None
        self._lock = threading.Lock()
        self._events_path: Optional[str] = None

    def start(self, meta: Dict[str, Any]) -> str:
        sid = _now_id()
        sdir = os.path.join(self.base_dir, sid)
        os.makedirs(os.path.join(sdir, "crops"), exist_ok=True)
        with open(os.path.join(sdir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        self._events_path = os.path.join(sdir, "events.jsonl")
        # touch file
        with open(self._events_path, "a", encoding="utf-8"):
            pass
        self.session_id = sid
        self.dir = sdir
        return sid

    def write_event(self, event: Dict[str, Any]) -> None:
        if not self._events_path:
            return
        with self._lock:
            with open(self._events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def save_crop(self, img_bgr: np.ndarray, name: str) -> Optional[str]:
        if not self.dir:
            return None
        rel = os.path.join("crops", name)
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            cv2.imwrite(path, img_bgr)
            return rel
        except Exception:
            return None

    @staticmethod
    def list_sessions(base_dir: str = "logs/sessions") -> List[str]:
        if not os.path.isdir(base_dir):
            return []
        out: List[str] = []
        for d in os.listdir(base_dir):
            p = os.path.join(base_dir, d)
            if os.path.isdir(p):
                out.append(d)
        out.sort(reverse=True)
        return out

