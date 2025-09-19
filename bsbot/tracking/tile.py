from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence, Tuple


@dataclass
class TilePosition:
    row: int
    col: int
    confidence: float
    last_seen: float
    vx: int = 0
    vy: int = 0


class TileGrid:
    """Helper that converts between screen pixels and tile coordinates."""

    def __init__(
        self,
        tile_size: float,
        *,
        roi_origin: Tuple[int, int] = (0, 0),
        tile_origin: Tuple[float, float] = (0.0, 0.0),
        hover_offset: Tuple[float, float] = (0.5, 0.5),
    ) -> None:
        if tile_size <= 0:
            raise ValueError("tile_size must be > 0")
        self.tile_size = float(tile_size)
        self.roi_origin = roi_origin
        self.tile_origin = tile_origin
        self.hover_offset = hover_offset

    # -- Conversion helpers -------------------------------------------------
    def screen_to_tile(self, x: float, y: float) -> Tuple[int, int]:
        """Convert absolute screen coords to tile indices."""
        rel_x = (x - self.roi_origin[0]) - self.tile_origin[0]
        rel_y = (y - self.roi_origin[1]) - self.tile_origin[1]
        col = int(rel_x // self.tile_size)
        row = int(rel_y // self.tile_size)
        return row, col

    def tile_to_screen(self, row: int, col: int) -> Tuple[float, float]:
        """Return the top-left pixel for the given tile (absolute screen coords)."""
        x = self.roi_origin[0] + self.tile_origin[0] + col * self.tile_size
        y = self.roi_origin[1] + self.tile_origin[1] + row * self.tile_size
        return x, y

    def tile_center(self, row: int, col: int) -> Tuple[float, float]:
        """Return absolute pixel center for a tile."""
        x, y = self.tile_to_screen(row, col)
        cx = x + self.tile_size * 0.5
        cy = y + self.tile_size * 0.5
        return cx, cy

    def tile_rect(self, row: int, col: int) -> Tuple[int, int, int, int]:
        """Return integer ROI-relative rect for the tile (x, y, w, h)."""
        x, y = self.tile_to_screen(row, col)
        return (
            int(x - self.roi_origin[0]),
            int(y - self.roi_origin[1]),
            int(self.tile_size),
            int(self.tile_size),
        )

    def context_menu_rect(self, row: int, col: int) -> Tuple[int, int, int, int]:
        """Heuristic ROI for the action menu relative to a tile."""
        x, y, w, h = self.tile_rect(row, col)
        menu_x = x + w
        menu_y = int(y - 0.25 * h)
        menu_w = int(w * 1.4)
        menu_h = int(h * 1.7)
        return menu_x, menu_y, menu_w, menu_h

    def hover_label_rect(self, row: int, col: int) -> Tuple[int, int, int, int]:
        """ROI just above the tile where floating labels appear."""
        x, y, w, h = self.tile_rect(row, col)
        label_w = int(w * 1.2)
        label_h = int(h * 0.6)
        label_x = int(x - 0.1 * w)
        label_y = int(y - label_h - 0.1 * h)
        return label_x, label_y, label_w, label_h

    def player_tile(self, roi_width: int, roi_height: int) -> Tuple[int, int]:
        px = self.roi_origin[0] + self.tile_origin[0] + roi_width * self.hover_offset[0]
        py = self.roi_origin[1] + self.tile_origin[1] + roi_height * self.hover_offset[1]
        return self.screen_to_tile(px, py)

    @staticmethod
    def is_adjacent(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
        return max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1

    @classmethod
    def from_samples(
        cls,
        samples: Sequence[Tuple[Tuple[float, float], Tuple[int, int]]],
        *,
        roi_origin: Tuple[int, int] = (0, 0),
        hover_offset: Tuple[float, float] = (0.5, 0.5),
    ) -> "TileGrid":
        result = calibrate_tile_grid(samples)
        return cls(
            result.tile_size,
            roi_origin=roi_origin,
            tile_origin=result.tile_origin,
            hover_offset=hover_offset,
        )


class TileTracker:
    """Simple lifetime tracker that predicts tile movement."""

    def __init__(self, *, max_age: float = 0.6) -> None:
        self._tracks: Dict[str, TilePosition] = {}
        self.max_age = max_age

    def update(
        self,
        key: str,
        row: int,
        col: int,
        confidence: float,
        *,
        timestamp: Optional[float] = None,
    ) -> TilePosition:
        ts = timestamp or time.time()
        prev = self._tracks.get(key)
        vx = vy = 0
        if prev:
            dt = max(ts - prev.last_seen, 1e-6)
            vx = col - prev.col
            vy = row - prev.row
            if dt > 0 and abs(vx) > 1:
                vx = max(-1, min(1, vx))
            if dt > 0 and abs(vy) > 1:
                vy = max(-1, min(1, vy))
        track = TilePosition(row=row, col=col, confidence=confidence, last_seen=ts, vx=vx, vy=vy)
        self._tracks[key] = track
        return track

    def mark_missed(self, key: str) -> None:
        if key in self._tracks:
            self._tracks[key].confidence *= 0.9

    def predict(self, key: str, *, timestamp: Optional[float] = None) -> Optional[TilePosition]:
        track = self._tracks.get(key)
        if not track:
            return None
        ts = timestamp or time.time()
        if ts - track.last_seen > self.max_age:
            self._tracks.pop(key, None)
            return None
        return track

    def prune(self) -> None:
        now_ts = time.time()
        stale = [k for k, v in self._tracks.items() if now_ts - v.last_seen > self.max_age]
        for key in stale:
            self._tracks.pop(key, None)

    def clear(self) -> None:
        self._tracks.clear()


@dataclass
class TileCalibrationResult:
    tile_size: float
    tile_origin: Tuple[float, float]
    error_px: float


def calibrate_tile_grid(
    samples: Sequence[Tuple[Tuple[float, float], Tuple[int, int]]]
) -> TileCalibrationResult:
    """Estimate tile size/origin from sample correspondences.

    Args:
        samples: Iterable of ((screen_x, screen_y), (row, col)).
    Returns:
        TileCalibrationResult with average error in pixels.
    """

    if not samples:
        raise ValueError("At least one sample required for calibration")
    sx: list[float] = []
    sy: list[float] = []
    rows: list[int] = []
    cols: list[int] = []
    for (px, py), (row, col) in samples:
        sx.append(float(px))
        sy.append(float(py))
        rows.append(int(row))
        cols.append(int(col))

    # Estimate tile size using pairwise differences along rows/cols
    col_diffs: list[float] = []
    row_diffs: list[float] = []
    n = len(samples)
    for i in range(n):
        for j in range(i + 1, n):
            dc = cols[j] - cols[i]
            dr = rows[j] - rows[i]
            if dc:
                col_diffs.append(abs((sx[j] - sx[i]) / dc))
            if dr:
                row_diffs.append(abs((sy[j] - sy[i]) / dr))
    estimates = [d for d in col_diffs + row_diffs if d > 0]
    if not estimates:
        raise ValueError("Insufficient variance in calibration samples")
    tile_size = sum(estimates) / len(estimates)

    origin_x_terms = [sx[i] - cols[i] * tile_size for i in range(n)]
    origin_y_terms = [sy[i] - rows[i] * tile_size for i in range(n)]
    origin_x = sum(origin_x_terms) / len(origin_x_terms)
    origin_y = sum(origin_y_terms) / len(origin_y_terms)

    # Compute average error
    total_err = 0.0
    for (px, py), (row, col) in samples:
        ex = origin_x + col * tile_size
        ey = origin_y + row * tile_size
        total_err += ((ex - px) ** 2 + (ey - py) ** 2) ** 0.5
    error_px = total_err / len(samples)
    return TileCalibrationResult(tile_size=tile_size, tile_origin=(origin_x, origin_y), error_px=error_px)
