"""Add the prefix+m binding to the user's herdr config, carefully.

The original text is never rewritten: the block is appended, so comments and
formatting stay exactly as they were.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from datetime import datetime
from pathlib import Path

KEY = "prefix+m"
ACTION = "local.steps.mark"
BLOCK = (
    "\n# herdr-steps: pin agent instructions\n"
    "[[keys.command]]\n"
    f'key = "{KEY}"\n'
    'type = "plugin_action"\n'
    f'command = "{ACTION}"\n'
    'description = "pin agent steps"\n'
)


def _is_our_key(value: object) -> bool:
    # Conservative: any spelling that might mean prefix+m counts as a clash.
    return isinstance(value, str) and value.replace(" ", "").lower() == KEY


def _find_binding(keys: dict) -> str | None:
    """Return "ours", a description of the clashing binding, or None."""
    for entry in keys.get("command") or []:
        if isinstance(entry, dict) and _is_our_key(entry.get("key")):
            if entry.get("command") == ACTION:
                return "ours"
            return f"command {entry.get('command', '?')}"
    for name, value in keys.items():
        if name == "command":
            continue
        values = value if isinstance(value, list) else [value]
        if any(_is_our_key(v) for v in values):
            return name
    return None


def ensure_binding(config_text: str) -> tuple[str, str]:
    try:
        parsed = tomllib.loads(config_text)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"config.toml is not valid TOML: {e}") from e
    keys = parsed.get("keys")
    found = _find_binding(keys) if isinstance(keys, dict) else None
    if found == "ours":
        return config_text, "already"
    if found:
        return config_text, f"conflict:{found}"
    base = config_text
    if base and not base.endswith("\n"):
        base += "\n"
    new_text = base + BLOCK
    try:
        # An inline `keys.command = [...]` or `keys = {...}` can't be extended
        # by appending a [[keys.command]] table; never write a broken file.
        tomllib.loads(new_text)
    except tomllib.TOMLDecodeError:
        return config_text, "conflict:inline keys (add the binding by hand)"
    return new_text, "added"


def apply_binding(config_path: Path, now: datetime) -> str:
    config_path = Path(config_path)
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(BLOCK.lstrip())
        return "added"
    original = config_path.read_text()
    new_text, status = ensure_binding(original)
    if status == "added":
        backup = config_path.with_name(
            f"{config_path.name}.bak-herdr-steps-{now.strftime('%Y%m%d-%H%M%S')}"
        )
        shutil.copy2(config_path, backup)
        tmp = config_path.with_name(config_path.name + ".herdr-steps-tmp")
        tmp.write_text(new_text)
        os.replace(tmp, config_path)
    return status
