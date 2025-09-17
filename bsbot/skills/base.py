from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from bsbot.runtime.service import DetectorRuntime


@dataclass
class FrameContext:
    """Metadata about the current capture frame passed to a skill."""

    hwnd: Optional[int]
    window_rect: Tuple[int, int, int, int]
    roi_origin: Tuple[int, int]
    roi_size: Tuple[int, int]


class SkillController(ABC):
    """Contract for skill-specific controllers that drive detection and actions."""

    name: str = "base"

    def __init__(self, runtime: "DetectorRuntime") -> None:
        self.runtime = runtime

    # Lifecycle hooks -----------------------------------------------------
    def on_start(self, params: Dict[str, Any] | None = None) -> None:
        """Called when the runtime transitions into this skill."""
        return None

    def on_update_params(self, params: Dict[str, Any] | None = None) -> None:
        """Called when start parameters are updated while running."""
        return None

    def on_stop(self) -> None:
        """Called when the runtime stops the skill."""
        return None

    def snapshot(self) -> Dict[str, Any]:
        """Optional per-skill snapshot data to expose via API."""
        return {}

    # Frame processing ----------------------------------------------------
    @abstractmethod
    def process_frame(self, frame, ctx: FrameContext) -> Tuple[Dict[str, Any], Optional[bytes]]:
        """Process the captured frame and return status + optional preview."""
        raise NotImplementedError
