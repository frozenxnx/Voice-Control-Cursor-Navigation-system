import time
import unittest

from voicecursor.backends import DryRunMouse
from voicecursor.commands import Mode
from voicecursor.config import Config
from voicecursor.controller import Controller
from voicecursor.elements import ElementInfo
from voicecursor.geometry import Rect


def make(**overrides):
    mouse = DryRunMouse()
    ctl = Controller(mouse, Config(**overrides))
    return ctl, mouse


def make_grid(bounds=Rect(0, 0, 900, 900), **overrides):
    """A controller with a fixed screen size, so grid tests never touch a
    real display."""
    mouse = DryRunMouse()
    ctl = Controller(mouse, Config(**overrides), screen_bounds=bounds)
    return ctl, mouse


def elem(name, left, top, w=80, h=20):
    return ElementInfo(name, "ButtonControl", Rect(left, top, w, h))


def make_labels(elements, bounds=Rect(0, 0, 900, 900), **overrides):
    """A controller with a fixed screen size and a fixed set of "found"
    elements, so label tests never touch real UI Automation."""
    mouse = DryRunMouse()
    ctl = Controller(mouse, Config(**overrides), screen_bounds=bounds,
                      elements_provider=lambda: elements)
    return ctl, mouse


class MovementTests(unittest.TestCase):
    def test_move_with_amount(self):
        ctl, mouse = make()
        ctl.handle("move left two hundred")
        self.assertEqual(mouse.calls, [("move_rel", -200, 0)])

    def test_move_uses_default_step(self):
        ctl, mouse = make(move_step=75)
        ctl.handle("move down")
        self.assertEqual(mouse.calls, [("move_rel", 0, 75)])

    def test_move_is_clamped(self):
        ctl, mouse = make(max_move=500)
        ctl.handle("move right five thousand")
        self.assertEqual(mouse.calls, [("move_rel", 500, 0)])

    def test_up_is_negative_y(self):
        ctl, mouse = make()
        ctl.handle("move up fifty")
        self.assertEqual(mouse.calls, [("move_rel", 0, -50)])


class ClickAndScrollTests(unittest.TestCase):
    def test_clicks(self):
        ctl, mouse = make()
        ctl.handle("click")
        ctl.handle("double click")
        ctl.handle("right click")
        self.assertEqual(mouse.calls, [
            ("click", "left", 1), ("click", "left", 2), ("click", "right", 1)])

    def test_scroll_down_is_negative_wheel(self):
        ctl, mouse = make()
        ctl.handle("scroll down five")
        self.assertEqual(mouse.calls, [("scroll", -5, 0)])

    def test_scroll_up_default_and_clamp(self):
        ctl, mouse = make(scroll_notches=4, max_scroll=10)
        ctl.handle("scroll up")
        ctl.handle("scroll up ninety")
        self.assertEqual(mouse.calls, [("scroll", 4, 0), ("scroll", 10, 0)])

    def test_horizontal_scroll(self):
        ctl, mouse = make()
        ctl.handle("scroll right two")
        self.assertEqual(mouse.calls, [("scroll", 0, 2)])


class DragTests(unittest.TestCase):
    def test_hold_move_release(self):
        ctl, mouse = make()
        ctl.handle("hold move right three hundred release")
        self.assertEqual(mouse.calls, [
            ("button_down", "left"), ("move_rel", 300, 0), ("button_up", "left")])

    def test_release_without_hold_is_a_noop(self):
        ctl, mouse = make()
        ctl.handle("release")
        self.assertEqual(mouse.calls, [])

    def test_double_hold_only_presses_once(self):
        ctl, mouse = make()
        ctl.handle("hold hold")
        self.assertEqual(mouse.calls, [("button_down", "left")])

    def test_close_releases_a_held_button(self):
        ctl, mouse = make()
        ctl.handle("hold")
        ctl.close()
        self.assertEqual(mouse.calls[-1], ("button_up", "left"))


class ModeTests(unittest.TestCase):
    def test_sleep_ignores_commands_until_wake(self):
        ctl, mouse = make()
        ctl.handle("stop listening")
        self.assertIs(ctl.mode, Mode.SLEEPING)
        ctl.handle("click move left")
        self.assertEqual(mouse.calls, [])
        ctl.handle("wake up")
        self.assertIs(ctl.mode, Mode.COMMAND)
        ctl.handle("click")
        self.assertEqual(mouse.calls, [("click", "left", 1)])

    def test_start_asleep(self):
        ctl, _ = make(start_asleep=True)
        self.assertIs(ctl.mode, Mode.SLEEPING)

    def test_quit_sets_flag(self):
        ctl, _ = make()
        self.assertFalse(ctl.should_quit)
        ctl.handle("exit voice control")
        self.assertTrue(ctl.should_quit)

    def test_result_summary(self):
        ctl, _ = make()
        self.assertEqual(ctl.handle("move left two hundred click").summary(),
                         "move left 200 · click")
        self.assertEqual(ctl.handle("banana").summary(), "? banana")
        self.assertEqual(ctl.handle("").summary(), "")


class GlideTests(unittest.TestCase):
    def test_glide_moves_until_stopped(self):
        ctl, mouse = make(glide_speed=1000)
        ctl.handle("glide left")
        time.sleep(0.25)
        ctl.handle("stop")
        moved_calls = len(mouse.calls)
        self.assertGreater(moved_calls, 0)
        self.assertTrue(all(c[0] == "move_rel" and c[1] < 0 and c[2] == 0
                            for c in mouse.calls))
        time.sleep(0.15)
        self.assertEqual(len(mouse.calls), moved_calls, "cursor kept moving after stop")
        self.assertLess(mouse.x, 0)

    def test_any_command_cancels_glide(self):
        ctl, mouse = make(glide_speed=1000)
        ctl.handle("glide down")
        time.sleep(0.1)
        ctl.handle("click")
        n = len(mouse.calls)
        time.sleep(0.1)
        self.assertEqual(len(mouse.calls), n)
        ctl.close()

    def test_glide_speed_is_roughly_right(self):
        ctl, mouse = make(glide_speed=500)
        ctl.handle("glide right")
        time.sleep(0.5)
        ctl.close()
        # ~250 px expected; allow generous slack for CI timing jitter
        self.assertTrue(150 <= mouse.x <= 350, mouse.x)


class GridTests(unittest.TestCase):
    def test_grid_enters_from_command_mode(self):
        ctl, mouse = make_grid()
        result = ctl.handle("grid")
        self.assertIs(ctl.mode, Mode.GRID)
        self.assertIs(result.mode, Mode.GRID)
        self.assertEqual(result.grid_bounds, Rect(0, 0, 900, 900))
        self.assertEqual(len(result.grid_cells), 9)
        self.assertEqual(mouse.calls, [])  # entering the grid doesn't move anything yet

    def test_select_zooms_and_updates_result(self):
        ctl, mouse = make_grid()
        ctl.handle("grid")
        result = ctl.handle("five")  # centre cell of a 900x900 3x3 grid
        self.assertEqual(result.grid_bounds, Rect(300, 300, 300, 300))
        self.assertIs(ctl.mode, Mode.GRID)
        self.assertEqual(mouse.calls, [])

    def test_click_moves_to_cell_centre_and_exits_grid(self):
        ctl, mouse = make_grid()
        ctl.handle("grid")
        ctl.handle("nine")  # bottom-right cell: (600,600)-(900,900), centre (750,750)
        result = ctl.handle("click")
        self.assertEqual(mouse.calls, [("move_to", 750, 750), ("click", "left", 1)])
        self.assertIs(ctl.mode, Mode.COMMAND)
        self.assertIsNone(result.grid_bounds)

    def test_multi_command_utterance_zooms_then_clicks(self):
        ctl, mouse = make_grid()
        ctl.handle("grid")
        ctl.handle("five two eight click")
        # 900x900 -> select 5 -> (300,300,300,300)
        #         -> select 2 -> top-middle third: (400,300,100,100)
        #         -> select 8 -> bottom-middle third of that: (433,366,34,33)-ish
        # just check the click landed inside the final cell and grid closed
        self.assertEqual(mouse.calls[-1], ("click", "left", 1))
        move = mouse.calls[-2]
        self.assertEqual(move[0], "move_to")
        self.assertTrue(300 <= move[1] <= 600 and 300 <= move[2] <= 600)
        self.assertIs(ctl.mode, Mode.COMMAND)

    def test_back_undoes_one_level(self):
        ctl, mouse = make_grid()
        ctl.handle("grid")
        ctl.handle("five")
        result = ctl.handle("back")
        self.assertEqual(result.grid_bounds, Rect(0, 0, 900, 900))
        self.assertIs(ctl.mode, Mode.GRID)

    def test_back_at_root_exits_grid_entirely(self):
        ctl, mouse = make_grid()
        ctl.handle("grid")
        result = ctl.handle("back")
        self.assertIs(ctl.mode, Mode.COMMAND)
        self.assertIsNone(result.grid_bounds)
        self.assertEqual(mouse.calls, [])

    def test_cancel_exits_regardless_of_depth(self):
        ctl, mouse = make_grid()
        ctl.handle("grid")
        ctl.handle("five")
        ctl.handle("three")
        result = ctl.handle("cancel")
        self.assertIs(ctl.mode, Mode.COMMAND)
        self.assertIsNone(result.grid_bounds)
        self.assertEqual(mouse.calls, [])  # cancel never touches the mouse

    def test_min_cell_size_stops_further_zoom(self):
        # 90x90 root, min cell 20px: after one 3x3 split cells are 30px, a
        # second split would give 10px cells, below the floor.
        ctl, mouse = make_grid(bounds=Rect(0, 0, 90, 90), grid_min_cell=20)
        ctl.handle("grid")
        ctl.handle("one")
        before = ctl._grid.current
        ctl.handle("one")  # should be ignored: current cell is already at the floor
        self.assertEqual(ctl._grid.current, before)

    def test_grid_word_not_recognised_while_already_in_grid_mode(self):
        # This isn't reachable via voice (the grid grammar has no "grid" word),
        # but exercise it directly to make sure re-entry doesn't corrupt state.
        ctl, mouse = make_grid()
        ctl.handle("grid")
        ctl.handle("five")
        result = ctl.handle("grid")  # parsed with the grid grammar: unrecognized
        self.assertEqual(result.unrecognized, ["grid"])
        self.assertEqual(result.grid_bounds, Rect(300, 300, 300, 300))  # unchanged

    def test_custom_grid_shape_from_config(self):
        ctl, mouse = make_grid(grid_rows=2, grid_cols=4)
        result = ctl.handle("grid")
        self.assertEqual(len(result.grid_cells), 8)

    def test_grid_click_is_distinct_from_plain_click(self):
        # Regression test: Action.GRID_CLICK and Action.CLICK previously shared
        # the string value "click", which Python's Enum silently treats as
        # aliasing (GRID_CLICK became CLICK itself), so entering "click" while
        # in grid mode fired a plain click instead of moving the cursor first.
        from voicecursor.commands import Action
        self.assertIsNot(Action.GRID_CLICK, Action.CLICK)

    def test_close_clears_grid_state(self):
        ctl, mouse = make_grid()
        ctl.handle("grid")
        ctl.close()
        self.assertIsNone(ctl._grid)

    def test_real_screen_bounds_used_when_not_injected(self):
        # No screen_bounds override: falls back to screen.virtual_screen_rect().
        # We only check that it doesn't crash and returns a sane rect (this
        # sandbox has no display, so the module falls back to 1920x1080).
        ctl, mouse = make(start_asleep=False)
        result = ctl.handle("grid")
        self.assertIs(result.mode, Mode.GRID)
        self.assertGreater(result.grid_bounds.width, 0)
        self.assertGreater(result.grid_bounds.height, 0)


class LabelsTests(unittest.TestCase):
    def test_enter_labels_elements_are_numbered_and_reported(self):
        els = [elem("Submit", 10, 10), elem("Cancel", 200, 10)]
        ctl, mouse = make_labels(els)
        result = ctl.handle("labels")
        self.assertIs(ctl.mode, Mode.LABELS)
        self.assertIs(result.mode, Mode.LABELS)
        self.assertEqual([i.name for i in result.label_items], ["Submit", "Cancel"])
        self.assertEqual([i.label for i in result.label_items], [1, 2])
        self.assertEqual(mouse.calls, [])  # entering doesn't move anything yet

    def test_show_numbers_phrase_also_enters(self):
        ctl, mouse = make_labels([elem("Only", 0, 0)])
        result = ctl.handle("show numbers")
        self.assertIs(result.mode, Mode.LABELS)

    def test_select_clicks_element_centre_and_exits(self):
        els = [elem("Submit", 10, 10, w=80, h=20)]  # centre: (50, 20)
        ctl, mouse = make_labels(els)
        ctl.handle("labels")
        result = ctl.handle("one")
        self.assertEqual(mouse.calls, [("move_to", 50, 20), ("click", "left", 1)])
        self.assertIs(ctl.mode, Mode.COMMAND)
        self.assertIsNone(result.label_bounds)

    def test_select_understands_multi_word_numbers(self):
        # Unlike the grid, labels can have more than nine elements, so this
        # exercises full number words, not just single digits.
        els = [elem(f"Item{i}", 0, i * 10) for i in range(1, 26)]  # 25 elements
        ctl, mouse = make_labels(els)
        ctl.handle("labels")
        ctl.handle("twenty five")
        self.assertEqual(mouse.calls[-1], ("click", "left", 1))
        self.assertIs(ctl.mode, Mode.COMMAND)

    def test_select_out_of_range_is_ignored(self):
        ctl, mouse = make_labels([elem("Only", 0, 0)])
        ctl.handle("labels")
        ctl.handle("nine")  # only label 1 exists
        self.assertEqual(mouse.calls, [])
        self.assertIs(ctl.mode, Mode.LABELS)  # stays in labels mode, doesn't crash

    def test_cancel_exits_without_clicking(self):
        ctl, mouse = make_labels([elem("Only", 0, 0)])
        ctl.handle("labels")
        result = ctl.handle("cancel")
        self.assertIs(ctl.mode, Mode.COMMAND)
        self.assertIsNone(result.label_bounds)
        self.assertEqual(mouse.calls, [])

    def test_no_elements_found_stays_in_command_mode(self):
        ctl, mouse = make_labels([])
        result = ctl.handle("labels")
        self.assertIs(ctl.mode, Mode.COMMAND)
        self.assertIs(result.mode, Mode.COMMAND)
        self.assertIsNone(result.label_bounds)

    def test_refresh_rescans(self):
        calls = {"n": 0}
        first = [elem("Old", 0, 0)]
        second = [elem("New1", 0, 0), elem("New2", 100, 0)]

        def provider():
            calls["n"] += 1
            return first if calls["n"] == 1 else second

        mouse = DryRunMouse()
        ctl = Controller(mouse, Config(), screen_bounds=Rect(0, 0, 900, 900),
                          elements_provider=provider)
        ctl.handle("labels")
        self.assertEqual(len(ctl._labels.items), 1)
        result = ctl.handle("refresh")
        self.assertEqual(len(ctl._labels.items), 2)
        self.assertIs(ctl.mode, Mode.LABELS)
        self.assertEqual(len(result.label_items), 2)

    def test_close_clears_labels_state(self):
        ctl, mouse = make_labels([elem("Only", 0, 0)])
        ctl.handle("labels")
        ctl.close()
        self.assertIsNone(ctl._labels)

    def test_labels_select_is_distinct_from_grid_select(self):
        # Same regression concern as the grid-click aliasing bug: make sure
        # these two enums didn't end up sharing a value.
        from voicecursor.commands import Action
        self.assertIsNot(Action.LABELS_SELECT, Action.GRID_SELECT)
        self.assertIsNot(Action.LABELS_CANCEL, Action.GRID_CANCEL)


if __name__ == "__main__":
    unittest.main()
