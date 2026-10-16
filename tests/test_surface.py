# -*- coding: utf-8 -*-
"""Offline tests for the smooth-surface grid and nodata-aware blur (numpy only)."""
import unittest

try:
    import numpy as np
    from fortyguard_heatmap.core import surface
    from fortyguard_heatmap.core.responses import ApiError
    HAVE_NUMPY = True
except Exception:  # system python without numpy
    HAVE_NUMPY = False


def _tile(k, x0, y0, size, value):
    return {"type": "Feature", "properties": {"tile_id": k, "value": value},
            "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + size, y0], [x0 + size, y0 + size],
                                                             [x0, y0 + size], [x0, y0]]]}}


def _grid(values, size=0.001):
    feats, k = [], 0
    for r, row in enumerate(values):
        for c, v in enumerate(row):
            feats.append(_tile(k, c * size, (len(values) - 1 - r) * size, size, v)); k += 1
    return {"type": "FeatureCollection", "features": feats}


@unittest.skipUnless(HAVE_NUMPY, "numpy not available")
class SurfaceTests(unittest.TestCase):
    def test_grid_paints_tiles_and_keeps_zero(self):
        md = _grid([[0.0, 2.0], [4.0, None]])
        values, mask, gt = surface.build_grid(md, "value", pixels_per_tile=4)
        self.assertEqual(values.shape, (3 * 4, 3 * 4))  # tiles + half-tile margin each side
        # half-tile margin = 2 px, so the top-left tile covers rows/cols 2..6 and the None tile 6..10
        self.assertTrue(mask[2:6, 2:6].all(), "tile at row 0 col 0 painted")
        self.assertEqual(values[2:6, 2:6].max(), 0.0)
        self.assertFalse(mask[6:10, 6:10].any(), "None tile stays unpainted")
        self.assertAlmostEqual(gt[1], 0.001 / 4)
        self.assertAlmostEqual(gt[5], -0.001 / 4)

    def test_blur_is_nodata_aware_and_bounded(self):
        md = _grid([[10.0, 20.0], [30.0, None]])
        values, mask, gt = surface.build_grid(md, "value", pixels_per_tile=4)
        out, valid = surface.gaussian_blur_nodata(values, mask, sigma_px=1.0)
        self.assertTrue(valid[2:6, 2:6].all())
        inside = out[valid]
        self.assertGreaterEqual(inside.min(), 10.0 - 1e-4)
        self.assertLessEqual(inside.max(), 30.0 + 1e-4)
        # centre of the 10-tile is still close to 10, the boundary between 10 and 20 is in between
        self.assertLess(abs(out[4, 4] - 10.0), 4.0)
        self.assertTrue(12.0 < out[4, 6] < 18.0)
        # pixels far from any tile remain NODATA
        self.assertEqual(out[0, 0], surface.NODATA)
        self.assertFalse(valid[0, 0])

    def test_zero_blur_returns_tiles(self):
        md = _grid([[1.0, 2.0]])
        values, mask, gt = surface.build_grid(md, "value", pixels_per_tile=2)
        out, valid = surface.gaussian_blur_nodata(values, mask, 0)
        self.assertTrue((out[valid] == values[valid]).all())

    def test_all_zero_tiles_are_valid_surface(self):
        md = _grid([[0.0, 0.0], [0.0, 0.0]])
        out, gt, st = surface.build_surface(md, "value")
        self.assertEqual(st["min"], 0.0)
        self.assertEqual(st["max"], 0.0)
        self.assertGreater(st["valid_pixels"], 0)

    def test_no_numeric_values_raises(self):
        md = _grid([[None, "x"]])
        with self.assertRaises(ApiError):
            surface.build_grid(md, "value")

    def test_supports_surface(self):
        self.assertTrue(surface.supports_surface("tcm"))
        self.assertTrue(surface.supports_surface("exceedance"))
        self.assertFalse(surface.supports_surface("time_of_measure"))

    def test_clip_to_polygon(self):
        try:
            import osgeo  # noqa: F401
        except ImportError:
            self.skipTest("GDAL (osgeo) not available outside QGIS")
        md = _grid([[5.0, 5.0], [5.0, 5.0]])
        values, mask, gt = surface.build_grid(md, "value", pixels_per_tile=4)
        out, valid = surface.gaussian_blur_nodata(values, mask, 1.0)
        # clip to the left half only
        poly = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [0.001, 0.0], [0.001, 0.002], [0.0, 0.002], [0.0, 0.0]]]}
        clipped, cvalid = surface.clip_to_polygon(out, valid, gt, poly)
        self.assertLess(cvalid.sum(), valid.sum())
        self.assertTrue(cvalid[4, 4])      # inside left tile
        self.assertFalse(cvalid[4, 8])     # inside right tile, outside polygon


if __name__ == "__main__":
    unittest.main()
