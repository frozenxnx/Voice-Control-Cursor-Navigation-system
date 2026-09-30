import unittest

from voicecursor.commands import Action, Command, Direction, Mode
from voicecursor.parser import (
    _SIMPLE_PHRASES, NUMBER_WORDS, parse, parse_grid, parse_labels, parse_number, vocabulary)


class EnumIntegrityTests(unittest.TestCase):
    """Python's Enum silently aliases members that share a value (the second
    name just becomes another name for the first), instead of raising an
    error. That bit us once already (GRID_CLICK was accidentally CLICK).
    This guards against it happening again for any Action or Mode member."""

    def test_no_duplicate_action_values(self):
        values = [a.value for a in Action]
        self.assertEqual(len(values), len(set(values)), values)

    def test_no_duplicate_mode_values(self):
        values = [m.value for m in Mode]
        self.assertEqual(len(values), len(set(values)), values)

L, R, U, D = Direction.LEFT, Direction.RIGHT, Direction.UP, Direction.DOWN


class ParseNumberTests(unittest.TestCase):
    def test_values(self):
        cases = {
            "five": 5,
            "fifteen": 15,
            "twenty": 20,
            "twenty five": 25,
            "hundred": 100,
            "one hundred": 100,
            "two hundred fifty": 250,
            "one hundred twenty five": 125,
            "fifteen hundred": 1500,
            "one thousand two hundred": 1200,
            "five thousand two hundred twenty one": 5221,
            "300": 300,
        }
        for text, expected in cases.items():
            with self.subTest(text):
                tokens = text.split()
                self.assertEqual(parse_number(tokens), (expected, len(tokens)))

    def test_stops_at_invalid_continuation(self):
        for text, expected, consumed in [
            ("five five", 5, 1),
            ("twenty thirty", 20, 1),
            ("one hundred hundred", 100, 2),
            ("two thousand thousand", 2000, 2),
        ]:
            with self.subTest(text):
                self.assertEqual(parse_number(text.split()), (expected, consumed))

    def test_no_number(self):
        self.assertEqual(parse_number(["click"], 0), (None, 0))
        self.assertEqual(parse_number([], 0), (None, 0))

    def test_respects_start_index(self):
        self.assertEqual(parse_number(["left", "two", "hundred"], 1), (200, 3))


class ParseCommandTests(unittest.TestCase):
    def cmds(self, text):
        return parse(text).commands

    def test_move_with_amount(self):
        self.assertEqual(self.cmds("move left two hundred"),
                         [Command(Action.MOVE, L, 200)])

    def test_move_without_amount_leaves_default_to_controller(self):
        self.assertEqual(self.cmds("move up"), [Command(Action.MOVE, U, None)])

    def test_bare_direction_is_a_move(self):
        self.assertEqual(self.cmds("down fifty"), [Command(Action.MOVE, D, 50)])

    def test_right_click_is_not_a_move(self):
        self.assertEqual(self.cmds("right click"), [Command(Action.RIGHT_CLICK)])

    def test_left_click_is_a_click(self):
        self.assertEqual(self.cmds("left click"), [Command(Action.CLICK)])

    def test_move_then_click_keeps_direction_with_the_move(self):
        self.assertEqual(self.cmds("move left click"),
                         [Command(Action.MOVE, L, None), Command(Action.CLICK)])

    def test_multiple_commands_in_one_utterance(self):
        self.assertEqual(
            self.cmds("move right three hundred double click"),
            [Command(Action.MOVE, R, 300), Command(Action.DOUBLE_CLICK)])

    def test_number_then_right_click(self):
        self.assertEqual(
            self.cmds("move left two right click"),
            [Command(Action.MOVE, L, 2), Command(Action.RIGHT_CLICK)])

    def test_scroll(self):
        self.assertEqual(self.cmds("scroll down five"), [Command(Action.SCROLL, D, 5)])
        self.assertEqual(self.cmds("scroll up"), [Command(Action.SCROLL, U, None)])

    def test_glide_and_stop(self):
        self.assertEqual(self.cmds("glide right stop"),
                         [Command(Action.GLIDE, R), Command(Action.STOP)])

    def test_stop_listening_beats_stop(self):
        self.assertEqual(self.cmds("stop listening"), [Command(Action.SLEEP)])

    def test_wake_phrases(self):
        self.assertEqual(self.cmds("wake up"), [Command(Action.WAKE)])
        self.assertEqual(self.cmds("start listening"), [Command(Action.WAKE)])

    def test_drag_sequence(self):
        self.assertEqual(
            self.cmds("hold move right three hundred release"),
            [Command(Action.HOLD), Command(Action.MOVE, R, 300), Command(Action.RELEASE)])

    def test_quit(self):
        self.assertEqual(self.cmds("exit voice control"), [Command(Action.QUIT)])

    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(self.cmds("  MOVE   Left  TWENTY "), [Command(Action.MOVE, L, 20)])

    def test_unknown_words_reported_but_skipped(self):
        result = parse("please move left banana")
        self.assertEqual(result.commands, [Command(Action.MOVE, L, None)])
        self.assertEqual(result.unrecognized, ["please", "banana"])

    def test_unk_token_is_silently_dropped(self):
        result = parse("[unk] click [unk]")
        self.assertEqual(result.commands, [Command(Action.CLICK)])
        self.assertEqual(result.unrecognized, [])

    def test_verb_without_direction_is_unrecognized(self):
        result = parse("move")
        self.assertEqual(result.commands, [])
        self.assertEqual(result.unrecognized, ["move"])

    def test_empty(self):
        self.assertEqual(parse("").commands, [])


class VocabularyTests(unittest.TestCase):
    def test_command_vocab_covers_every_word_the_parser_understands(self):
        vocab = set(vocabulary(Mode.COMMAND))
        for phrase in _SIMPLE_PHRASES:
            for word in phrase:
                self.assertIn(word, vocab)
        for word in NUMBER_WORDS | {"move", "scroll", "glide", "left", "right", "up", "down"}:
            self.assertIn(word, vocab)
        self.assertIn("[unk]", vocab)

    def test_sleeping_vocab_only_contains_wake_phrases(self):
        self.assertEqual(sorted(vocabulary(Mode.SLEEPING)),
                         sorted(["start listening", "wake up", "[unk]"]))

    def test_grid_vocab_is_small_and_closed(self):
        vocab = set(vocabulary(Mode.GRID))
        expected = {"one", "two", "three", "four", "five", "six", "seven",
                    "eight", "nine", "click", "back", "cancel", "[unk]"}
        self.assertEqual(vocab, expected)

    def test_labels_vocab_covers_full_numbers_and_controls(self):
        vocab = set(vocabulary(Mode.LABELS))
        self.assertTrue(NUMBER_WORDS.issubset(vocab))
        self.assertIn("cancel", vocab)
        self.assertIn("refresh", vocab)
        self.assertIn("[unk]", vocab)
        # unlike grid mode, this must support multi-word numbers like "twenty"
        self.assertIn("twenty", vocab)

    def test_command_vocab_includes_grid_entry_word(self):
        self.assertIn("grid", vocabulary(Mode.COMMAND))

    def test_command_vocab_includes_labels_entry_words(self):
        vocab = vocabulary(Mode.COMMAND)
        self.assertIn("labels", vocab)
        self.assertIn("show", vocab)
        self.assertIn("numbers", vocab)

    def test_vocab_has_no_duplicates(self):
        for mode in Mode:
            with self.subTest(mode=mode):
                vocab = vocabulary(mode)
                self.assertEqual(len(vocab), len(set(vocab)))


class ParseGridTests(unittest.TestCase):
    def cmds(self, text):
        return parse_grid(text).commands

    def test_digit_words(self):
        for word, n in [("one", 1), ("five", 5), ("nine", 9)]:
            with self.subTest(word):
                self.assertEqual(self.cmds(word), [Command(Action.GRID_SELECT, amount=n)])

    def test_numeric_digit_shorthand(self):
        self.assertEqual(self.cmds("7"), [Command(Action.GRID_SELECT, amount=7)])

    def test_zero_and_out_of_range_digits_are_unrecognized(self):
        result = parse_grid("0 10")
        self.assertEqual(result.commands, [])
        self.assertEqual(result.unrecognized, ["0", "10"])

    def test_control_words(self):
        self.assertEqual(self.cmds("click"), [Command(Action.GRID_CLICK)])
        self.assertEqual(self.cmds("back"), [Command(Action.GRID_BACK)])
        self.assertEqual(self.cmds("cancel"), [Command(Action.GRID_CANCEL)])

    def test_multiple_selects_then_click_in_one_utterance(self):
        self.assertEqual(
            self.cmds("five two eight click"),
            [Command(Action.GRID_SELECT, amount=5),
             Command(Action.GRID_SELECT, amount=2),
             Command(Action.GRID_SELECT, amount=8),
             Command(Action.GRID_CLICK)])

    def test_multi_word_numbers_are_not_understood_in_grid_mode(self):
        # "twenty" is not in the grid grammar at all (unlike parse(), which
        # understands full numbers); grid mode only ever needs single digits.
        result = parse_grid("twenty")
        self.assertEqual(result.commands, [])
        self.assertEqual(result.unrecognized, ["twenty"])

    def test_unk_token_dropped(self):
        result = parse_grid("[unk] five [unk]")
        self.assertEqual(result.commands, [Command(Action.GRID_SELECT, amount=5)])
        self.assertEqual(result.unrecognized, [])


class ParseLabelsTests(unittest.TestCase):
    def cmds(self, text):
        return parse_labels(text).commands

    def test_single_word_number(self):
        self.assertEqual(self.cmds("five"), [Command(Action.LABELS_SELECT, amount=5)])

    def test_multi_word_number_is_supported_unlike_grid(self):
        self.assertEqual(self.cmds("twenty five"), [Command(Action.LABELS_SELECT, amount=25)])

    def test_numeric_digit_shorthand(self):
        self.assertEqual(self.cmds("14"), [Command(Action.LABELS_SELECT, amount=14)])

    def test_cancel_and_refresh(self):
        self.assertEqual(self.cmds("cancel"), [Command(Action.LABELS_CANCEL)])
        self.assertEqual(self.cmds("refresh"), [Command(Action.LABELS_REFRESH)])

    def test_unk_token_dropped(self):
        result = parse_labels("[unk] five [unk]")
        self.assertEqual(result.commands, [Command(Action.LABELS_SELECT, amount=5)])
        self.assertEqual(result.unrecognized, [])

    def test_unrecognized_word(self):
        result = parse_labels("banana")
        self.assertEqual(result.commands, [])
        self.assertEqual(result.unrecognized, ["banana"])

    def test_empty(self):
        self.assertEqual(parse_labels("").commands, [])


if __name__ == "__main__":
    unittest.main()
