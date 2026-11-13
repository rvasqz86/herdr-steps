"""Turn a picked spot in a conversation into a frozen, tickable pin."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from steps.model import Pin, PinLine, Turn

SCROLLBACK_PIN_LINES = 200
NAME_MAX = 40
_STEP_RE = re.compile(r"^(\s*)(\d+[.)]|[-*•])\s+\S")


def snap_to_user(turns: list[Turn], index: int) -> int:
    if turns[index].role == "line":
        return index
    for i in range(index, -1, -1):
        if turns[i].role == "user":
            return i
    return index


def pin_range(turns: list[Turn], start: int) -> list[Turn]:
    if turns[start].role == "line":
        return turns[start : start + SCROLLBACK_PIN_LINES]
    end = len(turns)
    for i in range(start + 1, len(turns)):
        if turns[i].role == "user":
            end = i
            break
    return turns[start:end]


def _classify_text(text: str, next_id: int) -> tuple[list[PinLine], int]:
    out: list[PinLine] = []
    step_indent: int | None = None
    for line in text.split("\n"):
        m = _STEP_RE.match(line)
        if m:
            out.append(PinLine("step", line, next_id))
            step_indent = len(m.group(1))
            next_id += 1
        elif not line.strip():
            out.append(PinLine("blank", ""))
            step_indent = None
        elif step_indent is not None and len(line) - len(line.lstrip()) > step_indent:
            out.append(PinLine("text", line, next_id - 1))
        else:
            out.append(PinLine("text", line))
            step_indent = None
    return out, next_id


def classify_lines(turns: list[Turn]) -> list[PinLine]:
    out: list[PinLine] = []
    next_id = 0
    prev_role: str | None = None
    for turn in turns:
        # Scrollback lines are one continuous text; chat turns get a gap.
        if out and not (turn.role == "line" and prev_role == "line"):
            out.append(PinLine("blank", ""))
        if turn.role == "user":
            first, *rest = turn.text.strip("\n").split("\n")
            out.append(PinLine("user", "> " + first))
            out.extend(PinLine("user", "  " + r) for r in rest)
        elif turn.role == "tool":
            out.append(PinLine("tool", "⏺ " + turn.text))
        else:
            lines, next_id = _classify_text(turn.text, next_id)
            out.extend(lines)
        prev_role = turn.role
    return out


def default_name(turn: Turn) -> str:
    stripped = turn.text.strip()
    first = stripped.split("\n", 1)[0].strip() if stripped else ""
    return first[:NAME_MAX]


def build_pin(
    turns: list[Turn],
    picked: int,
    name: str,
    folder: str,
    source: str,
    agent: str | None,
    session_id: str | None,
    now: datetime,
) -> Pin:
    start = snap_to_user(turns, picked)
    return Pin(
        id=now.strftime("%Y%m%d-%H%M%S"),
        name=name,
        folder=folder,
        source=source,
        agent=agent,
        session_id=session_id,
        created_at=now.isoformat(timespec="seconds"),
        lines=classify_lines(pin_range(turns, start)),
        checked=set(),
    )


class PinStore:
    def __init__(self, state_dir: Path):
        self.dir = Path(state_dir) / "pins"

    def _path(self, pin_id: str) -> Path:
        return self.dir / f"{pin_id}.json"

    def save(self, pin: Pin) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(pin.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(pin.to_dict(), ensure_ascii=False, indent=1))
        os.replace(tmp, path)

    def _read(self, path: Path) -> Pin | None:
        try:
            return Pin.from_dict(json.loads(path.read_text()))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def load(self, pin_id: str) -> Pin | None:
        return self._read(self._path(pin_id))

    def list_for_folder(self, folder: str) -> list[Pin]:
        if not self.dir.is_dir():
            return []
        pins = [p for p in map(self._read, self.dir.glob("*.json")) if p]
        pins = [p for p in pins if p.folder == folder]
        return sorted(pins, key=lambda p: (p.created_at, p.id), reverse=True)

    def toggle(self, pin_id: str, step_id: int) -> Pin:
        pin = self.load(pin_id)
        if pin is None:
            raise KeyError(pin_id)
        pin.checked ^= {step_id}
        self.save(pin)
        return pin
