import unittest

from voicecursor.geometry import Rect
from voicecursor.grid import GridSelector


class GridSelectorTests(unittest.TestCase):
    def test_starts_at_full_bounds(self):
        bounds = Rect(0, 0, 900, 900)
        g = GridSelector(bounds)
        self.assertEqual(g.current, bounds)
        self.assertEqual(g.depth, 0)

    def test_cells_count_and_order(self):
        g = GridSelector(Rect(0, 0, 900, 900))
        self.assertEqual(len(g.cells), 9)
        self.assertEqual(g.cells, g.current.subdivide(3, 3))

    def test_select_zooms_in(self):
        g = GridSelector(Rect(0, 0, 900, 900))
        g.select(5)  # centre cell
        self.assertEqual(g.current, Rect(300, 300, 300, 300))
        self.assertEqual(g.depth, 1)
        g.select(1)  # top-left of the centre cell
        self.assertEqual(g.current, Rect(300, 300, 100, 100))
        self.assertEqual(g.depth, 2)

    def test_select_out_of_range_raises(self):
        g = GridSelector(Rect(0, 0, 900, 900))
        with self.assertRaises(ValueError):
            g.select(0)
        with self.assertRaises(ValueError):
            g.select(10)

    def test_back_undoes_one_level(self):
        g = GridSelector(Rect(0, 0, 900, 900))
        g.select(9)
        g.select(3)
        self.assertEqual(g.depth, 2)
        self.assertTrue(g.back())
        self.assertEqual(g.depth, 1)
        self.assertEqual(g.current, Rect(600, 600, 300, 300))

    def test_back_at_root_returns_false_and_stays_put(self):
        bounds = Rect(0, 0, 900, 900)
        g = GridSelector(bounds)
        self.assertFalse(g.back())
        self.assertEqual(g.current, bounds)
        self.assertEqual(g.depth, 0)

    def test_custom_rows_cols(self):
        g = GridSelector(Rect(0, 0, 100, 40), rows=2, cols=5)
        self.assertEqual(len(g.cells), 10)
        with self.assertRaises(ValueError):
            g.select(11)

    def test_invalid_grid_shape_raises(self):
        with self.assertRaises(ValueError):
            GridSelector(Rect(0, 0, 10, 10), rows=0)


if __name__ == "__main__":
    unittest.main()
