"""The frozen, tickable pin shown beside the live agent."""

from __future__ import annotations

import curses
import os
import textwrap

from steps.model import Pin

HELP = "space tick · ↑↓ step · q close"


class ViewerState:
    def __init__(self, pin: Pin):
        self.pin = pin
        self.step_rows = [i for i, l in enumerate(pin.lines) if l.kind == "step"]
        self._pos = 0 if self.step_rows else None
        self.scroll = 0

    @property
    def cursor_row(self) -> int | None:
        return None if self._pos is None else self.step_rows[self._pos]

    def header(self) -> str:
        done, total = self.pin.progress
        return f"★ {self.pin.name} · {done}/{total}"

    def move(self, delta: int) -> None:
        if self._pos is not None:
            self._pos = max(0, min(len(self.step_rows) - 1, self._pos + delta))

    def _toggle(self, row: int) -> int:
        step_id = self.pin.lines[row].step_id
        self.pin.checked ^= {step_id}
        return step_id

    def toggle_at_cursor(self) -> int | None:
        row = self.cursor_row
        return None if row is None else self._toggle(row)

    def toggle_row(self, row: int) -> int | None:
        if row not in self.step_rows:
            return None
        self._pos = self.step_rows.index(row)
        return self._toggle(row)


# ---------------------------------------------------------------- curses UI


def _layout(state: ViewerState, width: int) -> list[tuple[int, str]]:
    """Wrap pin lines to the pane width: list of (pin line index, text)."""
    out: list[tuple[int, str]] = []
    for i, line in enumerate(state.pin.lines):
        if line.kind == "step":
            box = "[x] " if line.step_id in state.pin.checked else "[ ] "
            body, indent = box + line.text.strip(), " " * 4
        elif line.kind == "text" and line.step_id is not None:
            body, indent = "    " + line.text.strip(), " " * 4
        else:
            body = line.text
            indent = " " * (len(body) - len(body.lstrip()) + (2 if line.kind == "user" else 0))
        if not body.strip():
            out.append((i, ""))
            continue
        wrapped = textwrap.wrap(body, max(10, width), subsequent_indent=indent,
                                drop_whitespace=False) or [body]
        out.extend((i, seg) for seg in wrapped)
    return out


def _put(win, y, x, text, attr=0):
    h, w = win.getmaxyx()
    if 0 <= y < h and x < w:
        try:
            win.addnstr(y, x, text, max(0, w - x - 1), attr)
        except curses.error:
            pass


def _viewer_loop(stdscr, state: ViewerState, on_change):
    from steps.picker import _colors

    curses.curs_set(0)
    colors = _colors()
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    curses.mouseinterval(0)
    body_top = 2
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        rows = _layout(state, w - 3)
        body_h = max(1, h - body_top - 1)
        # keep the cursor's first display row on screen
        if state.cursor_row is not None:
            cur = next((n for n, (i, _) in enumerate(rows) if i == state.cursor_row), 0)
            if cur < state.scroll:
                state.scroll = cur
            elif cur >= state.scroll + body_h:
                state.scroll = cur - body_h + 1
        state.scroll = max(0, min(state.scroll, max(0, len(rows) - body_h)))

        _put(stdscr, 0, 1, state.header(), colors["mark"])
        _put(stdscr, h - 1, 1, HELP + ("  ·  frozen copy" if w > 50 else ""), colors["dim"])
        visible = rows[state.scroll : state.scroll + body_h]
        for n, (i, text) in enumerate(visible):
            line = state.pin.lines[i]
            attr = 0
            if line.kind == "user":
                attr = colors["user"]
            elif line.kind == "tool":
                attr = colors["dim"]
            elif line.kind == "step" and line.step_id in state.pin.checked:
                attr = colors["done"]
            if i == state.cursor_row:
                attr |= curses.A_REVERSE
            _put(stdscr, body_top + n, 1, text, attr)
        stdscr.refresh()

        try:
            key = stdscr.get_wch()
        except curses.error:
            continue
        if key in ("q", "\x1b"):
            return
        if key == " " or key in ("\n", "\r", curses.KEY_ENTER):
            if state.toggle_at_cursor() is not None:
                on_change()
        elif key in (curses.KEY_UP, "k"):
            state.move(-1)
        elif key in (curses.KEY_DOWN, "j"):
            state.move(1)
        elif key == curses.KEY_PPAGE:
            state.scroll -= body_h
            state.move(-3)
        elif key == curses.KEY_NPAGE:
            state.scroll += body_h
            state.move(3)
        elif key == curses.KEY_MOUSE:
            try:
                _, _, my, _, bstate = curses.getmouse()
            except curses.error:
                continue
            if bstate & getattr(curses, "BUTTON4_PRESSED", 0):
                state.move(-1)
            elif bstate & getattr(curses, "BUTTON5_PRESSED", 0):
                state.move(1)
            elif bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                n = my - body_top
                if 0 <= n < len(visible) and state.toggle_row(visible[n][0]) is not None:
                    on_change()


def run_viewer(state: ViewerState, on_change) -> None:
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(_viewer_loop, state, on_change)
