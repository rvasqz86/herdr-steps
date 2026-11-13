"""Pick the best history source for a pane."""

from __future__ import annotations

from pathlib import Path

from steps.model import Turn
from steps.sources.claude import find_claude_session, read_claude_turns
from steps.sources.scrollback import scrollback_turns


def _claude_turns(pane: dict, home: Path) -> list[Turn]:
    session = (pane.get("agent_session") or {}).get("value")
    path = find_claude_session(session, pane.get("cwd") or "", home)
    return read_claude_turns(path) if path else []


def load_turns(pane: dict, herdr, home: Path) -> tuple[list[Turn], str]:
    if pane.get("agent") == "claude":
        try:
            turns = _claude_turns(pane, home)
        except Exception:  # any reader failure degrades to scrollback
            turns = []
        if turns:
            return turns, "claude"
    try:
        turns = scrollback_turns(herdr.pane_read(pane["pane_id"]))
    except Exception:
        turns = []
    if turns:
        return turns, "scrollback"
    return [], "none"
