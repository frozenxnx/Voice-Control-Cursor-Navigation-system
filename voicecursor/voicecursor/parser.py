"""Turn recognised text into Commands.

Vosk treats a grammar as a *vocabulary*: it may emit any sequence of the listed
words. So instead of enumerating every phrase ("move left 200", "move left 250",
...) we give the recogniser individual words and let this parser assemble them.
The vocabulary is derived from the tables below, so the two can't drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .commands import Action, Command, Direction, Mode

UNKNOWN_TOKEN = "[unk]"  # what Vosk emits for out-of-grammar audio

# --------------------------------------------------------------------------
# Number words
# --------------------------------------------------------------------------
_UNITS = {w: i for i, w in enumerate(
    ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"], start=1)}
_TEENS = {w: 10 + i for i, w in enumerate(
    ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
     "sixteen", "seventeen", "eighteen", "nineteen"])}
_TENS = {w: 10 * i for i, w in enumerate(
    ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"], start=2)}
NUMBER_WORDS = {*_UNITS, *_TEENS, *_TENS, "hundred", "thousand"}


def parse_number(tokens: Sequence[str], start: int = 0) -> tuple[int | None, int]:
    """Parse spoken digits starting at `start`.

    Returns (value, next_index), or (None, start) if no number is present.
    Stops at the first token that can't extend the number, so "five five"
    yields 5 (and leaves the second "five" unconsumed) rather than 10.
    """
    if start < len(tokens) and tokens[start].isdigit():  # handy for --text mode
        return int(tokens[start]), start + 1

    total = 0
    current = 0
    last: str | None = None
    used_thousand = False
    i = start
    while i < len(tokens):
        tok = tokens[i]
        if tok in _UNITS and last in (None, "tens", "hundred", "thousand"):
            current += _UNITS[tok]
            last = "unit"
        elif tok in _TEENS and last in (None, "hundred", "thousand"):
            current += _TEENS[tok]
            last = "teen"
        elif tok in _TENS and last in (None, "hundred", "thousand"):
            current += _TENS[tok]
            last = "tens"
        elif tok == "hundred" and last in (None, "unit", "teen") and current < 100:
            current = (current or 1) * 100  # "fifteen hundred" -> 1500
            last = "hundred"
        elif (tok == "thousand" and not used_thousand
              and last in (None, "unit", "teen", "tens", "hundred")):
            total += (current or 1) * 1000
            current = 0
            last = "thousand"
            used_thousand = True
        else:
            break
        i += 1

    if i == start:
        return None, start
    return total + current, i


# --------------------------------------------------------------------------
# Phrase tables
# --------------------------------------------------------------------------
_DIRECTIONS = {d.value: d for d in Direction}

# Fixed phrases with no arguments. Matched longest-first, so "right click"
# wins over the bare direction "right" and "stop listening" over "stop".
_SIMPLE_PHRASES: dict[tuple[str, ...], Action] = {
    ("double", "click"): Action.DOUBLE_CLICK,
    ("right", "click"): Action.RIGHT_CLICK,
    ("left", "click"): Action.CLICK,
    ("middle", "click"): Action.MIDDLE_CLICK,
    ("click",): Action.CLICK,
    ("hold",): Action.HOLD,
    ("release",): Action.RELEASE,
    ("stop",): Action.STOP,
    ("stop", "listening"): Action.SLEEP,
    ("go", "to", "sleep"): Action.SLEEP,
    ("sleep",): Action.SLEEP,
    ("start", "listening"): Action.WAKE,
    ("wake", "up"): Action.WAKE,
    ("exit", "voice", "control"): Action.QUIT,
    ("grid",): Action.GRID_ENTER,
    ("show", "numbers"): Action.LABELS_ENTER,
    ("labels",): Action.LABELS_ENTER,
}
_PHRASES = sorted(_SIMPLE_PHRASES.items(), key=lambda kv: -len(kv[0]))

# Verbs that take a direction (and, except glide, an optional number).
_VERBS = {"move", "scroll", "glide"}


# Grid mode: only cell numbers 1-9 plus a handful of control words. Keeping
# this vocabulary tiny is what makes grid recognition near-perfect.
_GRID_DIGITS = {w: n for w, n in _UNITS.items() if n <= 9}
_GRID_WORDS = {"click", "back", "cancel"}


def vocabulary(mode: Mode) -> list[str]:
    """Word list to hand to the speech recogniser for the given mode."""
    if mode is Mode.SLEEPING:
        # Whole phrases: the recogniser can then only "hear" the wake phrase.
        wake = [" ".join(p) for p, a in _SIMPLE_PHRASES.items() if a is Action.WAKE]
        return wake + [UNKNOWN_TOKEN]

    if mode is Mode.GRID:
        return sorted(set(_GRID_DIGITS) | _GRID_WORDS) + [UNKNOWN_TOKEN]

    if mode is Mode.LABELS:
        return sorted(NUMBER_WORDS | _LABELS_WORDS) + [UNKNOWN_TOKEN]

    words: set[str] = set(_VERBS) | set(_DIRECTIONS) | NUMBER_WORDS
    for phrase in _SIMPLE_PHRASES:
        words.update(phrase)
    return sorted(words) + [UNKNOWN_TOKEN]


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------
@dataclass
class ParseResult:
    commands: list[Command] = field(default_factory=list)
    unrecognized: list[str] = field(default_factory=list)


def _match_at(tokens: Sequence[str], i: int) -> tuple[Command | None, int]:
    """Try to read one command at tokens[i]. Returns (command, next_index);
    command is None if tokens[i] isn't understood (next_index is then i + 1)."""
    for phrase, action in _PHRASES:
        if tuple(tokens[i:i + len(phrase)]) == phrase:
            return Command(action), i + len(phrase)

    tok = tokens[i]
    if tok in _VERBS:
        if i + 1 < len(tokens) and tokens[i + 1] in _DIRECTIONS:
            direction = _DIRECTIONS[tokens[i + 1]]
            if tok == "glide":
                return Command(Action.GLIDE, direction), i + 2
            amount, nxt = parse_number(tokens, i + 2)
            action = Action.SCROLL if tok == "scroll" else Action.MOVE
            return Command(action, direction, amount), nxt
        return None, i + 1  # verb with no direction

    if tok in _DIRECTIONS:  # "left 200" is shorthand for "move left 200"
        amount, nxt = parse_number(tokens, i + 1)
        return Command(Action.MOVE, _DIRECTIONS[tok], amount), nxt

    return None, i + 1


_GRID_ACTIONS = {"click": Action.GRID_CLICK, "back": Action.GRID_BACK, "cancel": Action.GRID_CANCEL}


def parse_grid(text: str) -> ParseResult:
    """Parse an utterance heard while in Mode.GRID.

    A separate, tiny grammar rather than a branch inside parse(): grid mode
    only ever needs single-digit cell numbers, never the multi-word numbers
    ("twenty five") the movement commands use, so reusing parse_number here
    would accept phrases the grid grammar can't actually produce.
    """
    tokens = text.lower().split()
    result = ParseResult()
    for tok in tokens:
        if tok == UNKNOWN_TOKEN:
            continue
        if tok in _GRID_DIGITS:
            result.commands.append(Command(Action.GRID_SELECT, amount=_GRID_DIGITS[tok]))
        elif tok.isdigit() and 1 <= int(tok) <= 9:  # handy for --text mode
            result.commands.append(Command(Action.GRID_SELECT, amount=int(tok)))
        elif tok in _GRID_ACTIONS:
            result.commands.append(Command(_GRID_ACTIONS[tok]))
        else:
            result.unrecognized.append(tok)
    return result


# Labels mode: unlike the grid, there can be more than nine elements on
# screen, so this reuses parse_number's full multi-word number handling
# rather than the grid's single-digit-only shortcut.
_LABELS_WORDS = {"cancel", "refresh"}
_LABELS_ACTIONS = {"cancel": Action.LABELS_CANCEL, "refresh": Action.LABELS_REFRESH}


def parse_labels(text: str) -> ParseResult:
    """Parse an utterance heard while in Mode.LABELS."""
    tokens = text.lower().split()
    result = ParseResult()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == UNKNOWN_TOKEN:
            i += 1
            continue
        if tok in _LABELS_ACTIONS:
            result.commands.append(Command(_LABELS_ACTIONS[tok]))
            i += 1
            continue
        amount, nxt = parse_number(tokens, i)
        if amount is not None:
            result.commands.append(Command(Action.LABELS_SELECT, amount=amount))
            i = nxt
        else:
            result.unrecognized.append(tok)
            i += 1
    return result


def parse(text: str) -> ParseResult:
    """Parse an utterance into zero or more commands.

    Tolerant by design: unknown words are collected in `unrecognized` and
    skipped, and one utterance may contain several commands
    ("move left two hundred click").
    """
    tokens = text.lower().split()
    result = ParseResult()
    i = 0
    while i < len(tokens):
        if tokens[i] == UNKNOWN_TOKEN:
            i += 1
            continue
        command, nxt = _match_at(tokens, i)
        if command is not None:
            result.commands.append(command)
        else:
            result.unrecognized.append(tokens[i])
        i = nxt
    return result
