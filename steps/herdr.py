"""Thin wrapper over the herdr CLI ($HERDR_BIN_PATH)."""

from __future__ import annotations

import json
import os
import subprocess

PLUGIN_ID = "local.steps"


class HerdrError(Exception):
    pass


_DELETED = " (deleted)"


def _resolve_bin(path: str) -> str:
    """A server running from a since-replaced binary (e.g. after `herdr update`)
    reports "<path> (deleted)". Use the new file at <path>, else herdr on PATH."""
    if not path.endswith(_DELETED):
        return path
    stripped = path[: -len(_DELETED)]
    return stripped if os.path.exists(stripped) else "herdr"


class HerdrCli:
    def __init__(self, bin_path: str | None = None, run=subprocess.run):
        self.bin = _resolve_bin(bin_path or os.environ.get("HERDR_BIN_PATH") or "herdr")
        self._run = run

    def _call(self, *args: str) -> str:
        argv = [self.bin, *args]
        try:
            proc = self._run(argv, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise HerdrError(f"{' '.join(args[:3])}: {e}") from e
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise HerdrError(f"{' '.join(args[:3])} failed: {detail}")
        return proc.stdout

    def pane_get(self, pane_id: str) -> dict:
        out = self._call("pane", "get", pane_id)
        try:
            return json.loads(out)["result"]["pane"]
        except (ValueError, KeyError, TypeError) as e:
            raise HerdrError(f"unexpected pane get output: {out[:200]}") from e

    def pane_read(self, pane_id: str, lines: int = 2000) -> str:
        return self._call(
            "pane", "read", pane_id, "--source", "recent-unwrapped", "--lines", str(lines)
        )

    def open_pane(
        self,
        entrypoint: str,
        placement: str,
        target_pane: str | None = None,
        direction: str | None = None,
        width: str | None = None,
        height: str | None = None,
        env: dict[str, str] | None = None,
        focus: bool = True,
    ) -> None:
        args = [
            "plugin", "pane", "open", "--plugin", PLUGIN_ID,
            "--entrypoint", entrypoint, "--placement", placement,
        ]
        if target_pane:
            args += ["--target-pane", target_pane]
        if direction:
            args += ["--direction", direction]
        if width:
            args += ["--width", width]
        if height:
            args += ["--height", height]
        for key, value in (env or {}).items():
            args += ["--env", f"{key}={value}"]
        args.append("--focus" if focus else "--no-focus")
        self._call(*args)
