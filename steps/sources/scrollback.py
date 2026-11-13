"""Fallback: herdr's own scrollback, one turn per non-blank line."""

from __future__ import annotations

from steps.model import Turn


def scrollback_turns(text: str) -> list[Turn]:
    return [Turn("line", line.rstrip()) for line in text.split("\n") if line.strip()]
