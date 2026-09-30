import unittest

from voicecursor.geometry import Rect


class SubdivideTests(unittest.TestCase):
    def test_even_split_3x3(self):
        cells = Rect(0, 0, 900, 900).subdivide(3, 3)
        self.assertEqual(len(cells), 9)
        self.assertEqual(cells[0], Rect(0, 0, 300, 300))       # top-left
        self.assertEqual(cells[2], Rect(600, 0, 300, 300))     # top-right
        self.assertEqual(cells[4], Rect(300, 300, 300, 300))   # centre
        self.assertEqual(cells[8], Rect(600, 600, 300, 300))   # bottom-right

    def test_reading_order(self):
        # index 1 (second cell) must be adjacent to index 0, not below it.
        cells = Rect(0, 0, 300, 300).subdivide(3, 3)
        self.assertEqual(cells[0].top, cells[1].top)
        self.assertEqual(cells[0].right, cells[1].left)

    def test_uneven_split_has_no_gaps_or_overlap(self):
        r = Rect(10, 10, 1001, 767)
        for rows, cols in [(3, 3), (2, 5), (1, 7)]:
            with self.subTest(rows=rows, cols=cols):
                cells = r.subdivide(rows, cols)
                self.assertEqual(len(cells), rows * cols)
                # every cell in a row shares its right edge with the next cell's left edge
                for row in range(rows):
                    row_cells = cells[row * cols:(row + 1) * cols]
                    for a, b in zip(row_cells, row_cells[1:]):
                        self.assertEqual(a.right, b.left)
                    self.assertEqual(row_cells[0].left, r.left)
                    self.assertEqual(row_cells[-1].right, r.right)
                # every column shares its bottom edge with the next row's top edge
                for col in range(cols):
                    col_cells = cells[col::cols]
                    for a, b in zip(col_cells, col_cells[1:]):
                        self.assertEqual(a.bottom, b.top)
                    self.assertEqual(col_cells[0].top, r.top)
                    self.assertEqual(col_cells[-1].bottom, r.bottom)

    def test_non_square_grid(self):
        cells = Rect(0, 0, 100, 100).subdivide(1, 2)
        self.assertEqual(cells, [Rect(0, 0, 50, 100), Rect(50, 0, 50, 100)])


class PropertyTests(unittest.TestCase):
    def test_right_bottom(self):
        r = Rect(10, 20, 100, 50)
        self.assertEqual(r.right, 110)
        self.assertEqual(r.bottom, 70)

    def test_center(self):
        self.assertEqual(Rect(0, 0, 100, 100).center, (50, 50))
        self.assertEqual(Rect(10, 10, 101, 101).center, (60, 60))


if __name__ == "__main__":
    unittest.main()
