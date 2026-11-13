"""Read Claude Code's own session record (~/.claude/projects/<slug>/<id>.jsonl).

Files are only ever opened for reading. The agent may be appending while we
read, so lines that don't parse are skipped.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from steps.model import Turn

_WRAPPER_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<local-command-caveat>",
    "<system-reminder>",
)
_SUMMARY_MAX = 80


def find_claude_session(session_id: str | None, cwd: str, home: Path) -> Path | None:
    projects = home / ".claude" / "projects"
    if session_id:
        matches = sorted(projects.glob(f"*/{session_id}.jsonl"))
        if matches:
            return matches[0]
    slug = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    folder = projects / slug
    if not cwd or not folder.is_dir():
        return None
    files = list(folder.glob("*.jsonl"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _first_line(value: object) -> str:
    text = str(value or "").strip()
    return text.split("\n", 1)[0]


def _tool_summary(item: dict) -> str:
    raw_input = item.get("input")
    inp = raw_input if isinstance(raw_input, dict) else {}
    detail = _first_line(
        inp.get("description") or inp.get("command") or inp.get("file_path") or ""
    )
    name = item.get("name") or "tool"
    summary = f"{name}: {detail}" if detail else str(name)
    return summary[:_SUMMARY_MAX]


def _user_text(content: object) -> str | None:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        if not parts:
            return None  # tool results only
        text = "\n".join(parts)
    else:
        return None
    stripped = text.strip()
    if not stripped or stripped.startswith(_WRAPPER_PREFIXES):
        return None
    return text


def read_claude_turns(path: Path) -> list[Turn]:
    turns: list[Turn] = []

    def add(turn: Turn) -> None:
        if turn.role == "agent" and turns and turns[-1].role == "agent":
            prev = turns[-1]
            turns[-1] = Turn("agent", prev.text + "\n" + turn.text, prev.timestamp)
        else:
            turns.append(turn)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            kind = rec.get("type")
            if kind not in ("user", "assistant"):
                continue
            if rec.get("isSidechain") or rec.get("isMeta"):
                continue
            message = rec.get("message")
            if not isinstance(message, dict):
                continue
            ts = rec.get("timestamp")
            content = message.get("content")
            if kind == "user":
                text = _user_text(content)
                if text is not None:
                    add(Turn("user", text, ts))
                continue
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and item.get("text", "").strip():
                    add(Turn("agent", item["text"], ts))
                elif item.get("type") == "tool_use":
                    add(Turn("tool", _tool_summary(item), ts))
    return turns
