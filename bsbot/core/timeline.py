from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional


@dataclass
class Event:
    ts: str
    state: str
    type: str  # detect|click|confirm|timeout|retry|abort|transition|info
    label: str
    data: Dict[str, Any]


class Timeline:
    def __init__(self, maxlen: int = 200) -> None:
        self._buf: Deque[Event] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, state: str, type_: str, label: str, **data: Any) -> None:
        evt = Event(ts=datetime.utcnow().isoformat(timespec="milliseconds") + "Z", state=state, type=type_, label=label, data=data)
        with self._lock:
            self._buf.append(evt)

    def last(self, n: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._buf)[-n:]
        return [asdict(e) for e in items]


# Singleton timeline used by runtime and UI
timeline = Timeline()

