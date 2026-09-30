import unittest

from voicecursor.elements import ElementInfo
from voicecursor.geometry import Rect
from voicecursor.labels import LabelSelector, assign_labels


def elem(name, left, top, w=80, h=20, control_type="ButtonControl"):
    return ElementInfo(name, control_type, Rect(left, top, w, h))


class AssignLabelsTests(unittest.TestCase):
    def test_numbers_start_at_one(self):
        labeled = assign_labels([elem("Only", 0, 0)])
        self.assertEqual(labeled[0].label, 1)

    def test_reading_order_top_to_bottom_left_to_right(self):
        els = [
            elem("BottomLeft", 0, 200),
            elem("TopRight", 300, 0),
            elem("TopLeft", 0, 0),
            elem("BottomRight", 300, 200),
        ]
        labeled = assign_labels(els)
        self.assertEqual([e.name for e in labeled],
                         ["TopLeft", "TopRight", "BottomLeft", "BottomRight"])
        self.assertEqual([e.label for e in labeled], [1, 2, 3, 4])

    def test_same_row_sorted_left_to_right(self):
        els = [elem("Right", 500, 10), elem("Middle", 250, 10), elem("Left", 0, 10)]
        labeled = assign_labels(els)
        self.assertEqual([e.name for e in labeled], ["Left", "Middle", "Right"])

    def test_preserves_rect_and_name(self):
        [labeled] = assign_labels([elem("Submit", 5, 6, 70, 22)])
        self.assertEqual(labeled.name, "Submit")
        self.assertEqual(labeled.rect, Rect(5, 6, 70, 22))

    def test_empty_input(self):
        self.assertEqual(assign_labels([]), [])

    def test_exact_duplicate_rect_is_dropped(self):
        labeled = assign_labels([elem("Icon", 10, 10), elem("Button", 10, 10)])
        self.assertEqual(len(labeled), 1)

    def test_near_duplicate_within_tolerance_is_dropped(self):
        # off by 2px in each dimension - the kind of thing an icon nested in
        # its wrapping button commonly reports
        labeled = assign_labels([elem("A", 10, 10, 80, 20), elem("B", 12, 8, 78, 22)])
        self.assertEqual(len(labeled), 1)

    def test_distinct_elements_outside_tolerance_are_both_kept(self):
        labeled = assign_labels([elem("A", 10, 10), elem("B", 30, 10)])  # 20px apart
        self.assertEqual(len(labeled), 2)

    def test_duplicate_prefers_the_named_copy(self):
        # icon child (no name) discovered before its wrapping button (named)
        labeled = assign_labels([elem("", 10, 10), elem("Settings", 10, 10)])
        self.assertEqual(len(labeled), 1)
        self.assertEqual(labeled[0].name, "Settings")

    def test_duplicate_order_of_discovery_does_not_matter_for_naming(self):
        # named element discovered first this time
        labeled = assign_labels([elem("Settings", 10, 10), elem("", 10, 10)])
        self.assertEqual(len(labeled), 1)
        self.assertEqual(labeled[0].name, "Settings")

    def test_both_unnamed_duplicates_keeps_first(self):
        labeled = assign_labels([elem("", 10, 10, 80, 20), elem("", 10, 10, 79, 21)])
        self.assertEqual(len(labeled), 1)

    def test_dedup_then_numbering_stays_contiguous(self):
        els = [elem("A", 0, 0), elem("A-icon", 0, 0),  # duplicate pair
               elem("B", 0, 100), elem("C", 0, 200)]
        labeled = assign_labels(els)
        self.assertEqual([e.label for e in labeled], [1, 2, 3])
        self.assertEqual([e.name for e in labeled], ["A", "B", "C"])


class LabelSelectorTests(unittest.TestCase):
    def test_get_known_label(self):
        sel = LabelSelector(assign_labels([elem("A", 0, 0), elem("B", 0, 100)]))
        self.assertEqual(sel.get(1).name, "A")
        self.assertEqual(sel.get(2).name, "B")

    def test_get_unknown_label_returns_none(self):
        sel = LabelSelector(assign_labels([elem("A", 0, 0)]))
        self.assertIsNone(sel.get(2))
        self.assertIsNone(sel.get(0))

    def test_items_sorted_by_label(self):
        sel = LabelSelector(assign_labels([elem("A", 0, 0), elem("B", 0, 100), elem("C", 0, 200)]))
        self.assertEqual([e.label for e in sel.items], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
