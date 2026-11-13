"""The "where do the instructions start?" picker."""

from __future__ import annotations

import curses
from dataclasses import dataclass
from datetime import datetime, timezone

from steps.model import Pin, Turn

TITLE = "★ Where do the instructions start?"
HELP = "↑↓ move · enter pick · / search · esc close"


@dataclass
class Row:
    kind: str  # "pin" | "turn"
    label: str
    search_text: str
    is_user: bool
    ref: object  # Pin for "pin", index into turns for "turn"
    timestamp: str | None


def _first_line(text: str) -> str:
    stripped = text.strip()
    return stripped.split("\n", 1)[0] if stripped else ""


def rel_time(ts: str | None, now: datetime) -> str:
    if not ts:
        return ""
    try:
        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    secs = (now - when).total_seconds()
    if secs < 60:
        return "now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


class PickerState:
    def __init__(self, turns: list[Turn], pins: list[Pin]):
        self.rows: list[Row] = []
        for pin in pins:
            done, total = pin.progress
            label = f"★ {pin.name} · {done}/{total}"
            self.rows.append(Row("pin", label, pin.name, False, pin, pin.created_at))
        for i in range(len(turns) - 1, -1, -1):
            turn = turns[i]
            if turn.role == "tool":
                continue
            prefix = {"user": "> ", "agent": "⏺ "}.get(turn.role, "")
            self.rows.append(
                Row("turn", prefix + _first_line(turn.text), turn.text,
                    turn.role == "user", i, turn.timestamp)
            )
        self.query = ""
        self.visible = list(self.rows)
        self.index = 0

    def move(self, delta: int) -> None:
        if self.visible:
            self.index = max(0, min(len(self.visible) - 1, self.index + delta))

    def set_query(self, query: str) -> None:
        self.query = query
        q = query.lower()
        self.visible = [r for r in self.rows if q in r.search_text.lower()]
        self.index = 0

    def selected(self):
        if not self.visible:
            return None
        row = self.visible[self.index]
        return (row.kind, row.ref)


# ---------------------------------------------------------------- curses UI


def _colors() -> dict[str, int]:
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    curses.init_pair(1, curses.COLOR_YELLOW, bg)
    curses.init_pair(2, curses.COLOR_CYAN, bg)
    curses.init_pair(3, curses.COLOR_GREEN, bg)
    return {
        "mark": curses.color_pair(1) | curses.A_BOLD,
        "user": curses.color_pair(2),
        "done": curses.color_pair(3),
        "dim": curses.A_DIM,
    }


def _put(win, y: int, x: int, text: str, attr: int = 0) -> None:
    h, w = win.getmaxyx()
    if 0 <= y < h and x < w:
        try:
            win.addnstr(y, x, text, max(0, w - x - 1), attr)
        except curses.error:
            pass


def _pick_loop(stdscr, state: PickerState):
    curses.curs_set(0)
    colors = _colors()
    searching = False
    top = 0
    now = datetime.now(timezone.utc)
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        _put(stdscr, 0, 1, TITLE, colors["mark"])
        _put(stdscr, 0, max(len(TITLE) + 4, w - len(HELP) - 2), HELP, colors["dim"])
        if searching or state.query:
            _put(stdscr, 1, 1, f"/{state.query}" + ("█" if searching else ""))
        body_top, body_h = 3, max(1, h - 4)
        if state.index < top:
            top = state.index
        elif state.index >= top + body_h:
            top = state.index - body_h + 1
        if not state.visible:
            _put(stdscr, body_top, 3, "No matches", colors["dim"])
        for n, row in enumerate(state.visible[top : top + body_h]):
            y = body_top + n
            selected = top + n == state.index
            attr = curses.A_REVERSE if selected else 0
            if row.kind == "pin":
                attr |= colors["mark"]
            elif row.is_user:
                attr |= colors["user"]
            _put(stdscr, y, 1, f"{rel_time(row.timestamp, now):>8}", colors["dim"])
            _put(stdscr, y, 11, row.label.ljust(w), attr)
        stdscr.refresh()

        key = stdscr.get_wch()
        if searching:
            if key in ("\n", "\r", curses.KEY_ENTER):
                return state.selected()
            if key == "\x1b":
                searching = False
                state.set_query("")
            elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                state.set_query(state.query[:-1])
            elif key in (curses.KEY_UP, curses.KEY_DOWN):
                state.move(-1 if key == curses.KEY_UP else 1)
            elif isinstance(key, str) and key.isprintable():
                state.set_query(state.query + key)
            continue
        if key in ("q", "\x1b"):
            return None
        if key in ("\n", "\r", curses.KEY_ENTER):
            return state.selected()
        if key == "/":
            searching = True
        elif key in (curses.KEY_UP, "k"):
            state.move(-1)
        elif key in (curses.KEY_DOWN, "j"):
            state.move(1)
        elif key == curses.KEY_PPAGE:
            state.move(-body_h)
        elif key == curses.KEY_NPAGE:
            state.move(body_h)


def _name_loop(stdscr, default: str):
    curses.curs_set(1)
    colors = _colors()
    text = default
    while True:
        stdscr.erase()
        _put(stdscr, 0, 1, "★ Name this pin", colors["mark"])
        _put(stdscr, 0, 20, "enter save · esc cancel", colors["dim"])
        _put(stdscr, 2, 1, "> " + text)
        stdscr.move(2, min(3 + len(text), stdscr.getmaxyx()[1] - 2))
        stdscr.refresh()
        key = stdscr.get_wch()
        if key in ("\n", "\r", curses.KEY_ENTER):
            return text.strip() or default or "Pinned steps"
        if key == "\x1b":
            return None
        if key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            text = text[:-1]
        elif isinstance(key, str) and key.isprintable():
            text += key


def _message_loop(stdscr, text: str):
    curses.curs_set(0)
    colors = _colors()
    stdscr.erase()
    _put(stdscr, 1, 2, text)
    _put(stdscr, 3, 2, "press any key", colors["dim"])
    stdscr.refresh()
    stdscr.get_wch()


class CursesPickerUI:
    def __init__(self):
        import os

        os.environ.setdefault("ESCDELAY", "25")

    def message(self, text: str) -> None:
        curses.wrapper(_message_loop, text)

    def pick(self, state: PickerState):
        return curses.wrapper(_pick_loop, state)

    def ask_name(self, default: str):
        return curses.wrapper(_name_loop, default)
