import math
import unittest

from bsbot.tracking.tile import TileGrid, calibrate_tile_grid


class TileGridTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tile_size = 112.0
        self.origin = (5.3, 7.8)
        self.samples = [
            ((self.origin[0] + col * self.tile_size, self.origin[1] + row * self.tile_size), (row, col))
            for row in range(5)
            for col in range(5)
        ]

    def test_calibration_precision(self) -> None:
        result = calibrate_tile_grid(self.samples)
        self.assertAlmostEqual(result.tile_size, self.tile_size, delta=1e-3)
        self.assertLess(result.error_px, 1e-6)
        self.assertAlmostEqual(result.tile_origin[0], self.origin[0], delta=1e-3)
        self.assertAlmostEqual(result.tile_origin[1], self.origin[1], delta=1e-3)

    def test_round_trip_conversion(self) -> None:
        grid = TileGrid.from_samples(self.samples)
        max_err = 0.0
        for (sx, sy), (row, col) in self.samples:
            rr, cc = grid.screen_to_tile(sx + 0.4, sy + 0.6)
            self.assertEqual((rr, cc), (row, col))
            px, py = grid.tile_to_screen(row, col)
            max_err = max(max_err, math.hypot(px - sx, py - sy))
        self.assertLess(max_err, 1.0)

    def test_hover_rect_above_tile(self) -> None:
        grid = TileGrid(self.tile_size, tile_origin=self.origin)
        rect = grid.hover_label_rect(2, 3)
        x, y, w, h = rect
        self.assertLess(y, grid.tile_rect(2, 3)[1])
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
