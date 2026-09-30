# voicecursor

Hands-free cursor control for Windows. Offline speech recognition (Vosk) with a
small, grammar-constrained vocabulary, so commands are fast and accurate.

**Status: phase 3** - relative movement, clicks, scrolling, drag, sleep/wake,
grid navigation, and UI-element labels. Named-target clicking ("click
Submit") is next (see Roadmap).

## Quick start (Windows)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]

# Download a *small* English model and unzip into models/
# https://alphacephei.com/vosk/models  ->  vosk-model-small-en-us-0.15
python -m voicecursor --model models\vosk-model-small-en-us-0.15
```

Useful flags: `--list-devices`, `--device N`, `--start-asleep`, `--no-overlay`,
`--move-step 150`, `--glide-speed 600`, `-v`.

### Try it without a microphone

`--text` reads commands from stdin; `--dry-run` logs actions instead of moving
the cursor (it is also the automatic fallback on non-Windows systems).

```
echo move left two hundred | python -m voicecursor --text --dry-run
```

Run `--text` *without* `--dry-run` on Windows to test the real mouse backend
before involving speech recognition at all. That separates "my mic setup is
wrong" from "my SendInput code is wrong".

## Commands

| Say | Does |
|---|---|
| `move left two hundred` / `left 200` | Move the cursor (default 100 px if no number) |
| `glide right` ... `stop` | Move continuously until `stop` (or any other command) |
| `click`, `double click`, `right click`, `middle click` | Click at the cursor |
| `hold` ... `move right three hundred` ... `release` | Drag |
| `scroll down five`, `scroll up`, `scroll left two` | Scroll (default 3 notches) |
| `stop listening` / `go to sleep` | Ignore everything except the wake phrase |
| `start listening` / `wake up` | Resume |
| `exit voice control` | Quit (so it's usable without a keyboard) |

Several commands can share one utterance: *"move right three hundred double click"*.

### Grid navigation

Say `grid` to overlay a numbered 3x3 grid across every monitor. Say a number
to zoom into that cell (a fresh 3x3 grid appears inside it); repeat until
you're precise enough, then say `click`. `back` undoes one zoom (or exits the
grid if you're already at the top level); `cancel` exits immediately without
clicking.

| Say | Does |
|---|---|
| `grid` | Show the grid over the full (multi-monitor) screen |
| `one` ... `nine` | Zoom into that cell (reading order: 1-2-3 / 4-5-6 / 7-8-9) |
| `click` | Click at the centre of the current cell and exit the grid |
| `back` | Undo the last zoom (exits the grid from the top level) |
| `cancel` | Exit the grid without clicking |

Like other commands, a whole path can be said in one breath: *"grid five two
eight click"* zooms three times and clicks, all from one utterance. Grid mode
uses its own tiny vocabulary (just the digits 1-9 plus `click`/`back`/`cancel`),
so it's the most reliable way to move the cursor precisely - use it instead
of `move` when you need real accuracy.

There is a configurable floor (`grid_min_cell` in `config.py`, default 24 px)
below which further zooming is silently ignored, so an over-eager "five five
five..." can't zoom into nothing.

### UI element labels

Say `labels` (or `show numbers`) to scan the foreground window with Windows
UI Automation and overlay a numbered badge on every clickable control -
buttons, links, checkboxes, list items, tabs, menu items, and so on. Say the
number to click that element directly and exit; no grid navigation needed.

| Say | Does |
|---|---|
| `labels` / `show numbers` | Scan the foreground window and number its clickable elements |
| a number (`five`, `twenty three`, ...) | Click that element and exit label mode |
| `refresh` | Re-scan (the window may have scrolled or changed) without leaving label mode |
| `cancel` | Exit without clicking |

Numbers are assigned in reading order (top-to-bottom, then left-to-right), so
they land where you'd expect just by looking at the screen. Unlike the grid,
this understands full number words ("twenty three"), not just single digits,
since a busy window can easily have more than nine controls. If nothing
actionable is found, it silently stays in command mode instead of showing an
empty overlay.

This is the more natural tool for text-heavy apps (browsers, dialogs,
settings pages) where the thing you want has a name and a fixed position.
The grid is still there as a fallback for anything without a proper
accessibility tree (games, some custom-drawn UIs, older Win32 apps).

Both `grid` and `labels` share the same click-through overlay window under
the hood, and only one is ever active at a time.

## How it works

```
Mic -> MicStream -> VoskRecognizer -> parse() -> Controller -> MouseBackend
                         ^                            |             (Windows / DryRun)
                         +---- Mode (grammar) --------+--> Overlay
```

- **Grammar-constrained recognition.** Vosk gets a vocabulary of individual words,
  not every full phrase; `parser.py` assembles them (including spoken numbers).
  The vocabulary is generated from the parser's own tables, and a test keeps them in sync.
- **Modes swap the grammar.** `SLEEPING` can only hear the wake phrase; `GRID` can only
  hear digits 1-9 plus `click`/`back`/`cancel`; `LABELS` can only hear numbers (full words,
  not just 1-9) plus `cancel`/`refresh`. Each mode's vocabulary is as small as the task
  allows, which is most of why recognition stays reliable.
- **Grid and label math live outside tkinter.** `geometry.Rect`, `grid.GridSelector`, and
  `labels.LabelSelector`/`assign_labels` are pure, dependency-free and fully unit-tested;
  `screen.py` and `elements.py` isolate the platform-specific bits (screen size, UI
  Automation) so tests can inject fixed data instead.
- **UI element discovery is scoped and capped.** `elements.find_actionable_elements()`
  only walks the *foreground* window's UI Automation tree (not the whole desktop), and
  stops after `labels_max_elements` controls or `labels_max_depth` levels - an unscoped
  walk of a complex app can take seconds and make the overlay feel broken.
- **Near-duplicate elements are collapsed.** UI Automation sometimes exposes both a
  control and an almost pixel-identical wrapper/child for what's visually one clickable
  thing (an icon and its wrapping button, say), which otherwise shows up as two numbered
  badges stacked on each other. `labels._dedupe()` merges rects within a small tolerance,
  preferring whichever copy has a non-empty accessible name.
- **`SetCursorPos`, not relative `SendInput`.** Relative moves are subject to Windows
  pointer acceleration, so "200" would not mean 200 px. Clicks and wheel events use `SendInput`.
- **DPI awareness is enabled first thing**, before any coordinates are read - this matters
  even more for grid/labels than for `move`, since a wrong virtual-screen size misaligns
  the whole overlay.
- **Click-through overlay.** Grid and labels share one transparent, click-through window
  (only one mode is ever active at a time). Getting this right on Windows took a couple of
  rounds: colour-key transparency (`-transparentcolor`) is implemented via
  `SetLayeredWindowAttributes` under the hood, and touching the window's extended style
  (`WS_EX_TRANSPARENT` etc.) before that first paint can leave the whole window invisible
  instead of transparent. The fix was to defer applying click-through to one event-loop
  tick *after* the window's first real paint, rather than during setup.

## Known limitations

- **Elevated windows (UIPI).** Input can't be injected into apps running as administrator
  unless voicecursor is also elevated. Windows doesn't report this failure reliably,
  so the symptom is "nothing happens" in those windows only.
- **Small models only.** Runtime grammars need a model with a dynamic graph
  (`vosk-model-small-*`). Large models ignore the grammar.
- **Always listening.** There is no push-to-talk yet; use `--start-asleep` and the
  sleep/wake phrases to limit false triggers.
- **Primary-button swap.** Left-handed button swapping hasn't been tested.
- **Label coverage varies by app.** UI Automation support differs across toolkits - native
  Win32/WinUI apps tend to expose a rich tree; some Electron/Chromium apps expose a sparse
  one unless the app's own accessibility mode is active. When `labels` finds nothing, the
  grid is the fallback.
- **Labels are a one-time snapshot.** If the window scrolls or its content changes after
  you say `labels`, say `refresh` before selecting a number - selecting against a stale
  snapshot could click the wrong (or now-offscreen) element.

## Tests

```
python -m unittest discover -s tests -v     # or: pytest
```

110 tests, all platform-independent: the parser (including the grid and labels grammars),
grid math, label numbering/selection, mode machine, and glide logic. The Windows mouse
backend, microphone, Vosk, UI Automation scanning, and the tkinter overlay need real
hardware and a real display, so they are **not** covered by automated tests. The grid
overlay *has* been confirmed working on real Windows (rendering, click-through, and
voice-driven clicks all verified); the labels overlay reuses the same window/rendering
code path but hasn't been visually confirmed yet - if the numbered badges don't show up
or land in the wrong spot, that's the first thing to report back.

If you ever need to debug the overlay in isolation again, `python -m voicecursor
--test-grid` shows the grid immediately with no mic/Vosk involved at all.

## Roadmap

1. ~~Voice commands, relative movement, clicks, scrolling~~ (phase 1)
2. ~~Grid overlay: recursive 3x3 numbered zoom ("nine", "four", "click")~~ (phase 2)
3. ~~UI Automation element labels: "show numbers", "click fourteen"~~ (this release)
4. Named targets ("click Submit") with fuzzy matching over the same UI Automation scan
5. Settings file, tray icon, push-to-talk hotkey, custom commands
6. Benchmark harness: recorded WAVs -> accuracy and latency numbers
