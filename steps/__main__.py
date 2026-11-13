"""Entry points: python3 -m steps mark|picker|pin|setup."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from steps.herdr import HerdrCli, HerdrError
from steps.pins import PinStore, build_pin, default_name, snap_to_user
from steps.sources import load_turns

NOTHING_TO_PIN = "Nothing to pin in this pane yet"


def cmd_mark(env, herdr) -> int:
    try:
        context = json.loads(env.get("HERDR_PLUGIN_CONTEXT_JSON") or "{}")
    except ValueError:
        context = {}
    pane = context.get("focused_pane_id")
    if not pane:
        print("herdr-steps: no focused pane to pin from", file=sys.stderr)
        return 1
    try:
        herdr.open_pane(
            "picker", "popup", width="80%", height="70%",
            env={"HERDR_STEPS_SOURCE_PANE": pane},
        )
    except HerdrError as e:
        if "ui_busy" in str(e):
            print("herdr-steps: close copy mode or the open menu first", file=sys.stderr)
        else:
            print(f"herdr-steps: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_picker(env, herdr, home: Path, ui, now: datetime) -> int:
    pane_id = env.get("HERDR_STEPS_SOURCE_PANE")
    if not pane_id:
        ui.message("herdr-steps: no source pane was given")
        return 1
    try:
        pane = herdr.pane_get(pane_id)
    except HerdrError as e:
        ui.message(f"herdr-steps: {e}")
        return 1
    folder = pane.get("cwd") or ""
    store = PinStore(Path(env["HERDR_PLUGIN_STATE_DIR"]))
    pins = store.list_for_folder(folder)
    turns, source = load_turns(pane, herdr, home)
    if not turns and not pins:
        ui.message(NOTHING_TO_PIN)
        return 0

    from steps.picker import PickerState

    choice = ui.pick(PickerState(turns, pins))
    if choice is None:
        return 0
    kind, ref = choice
    if kind == "pin":
        pin = ref
    else:
        name = ui.ask_name(default_name(turns[snap_to_user(turns, ref)]))
        if name is None:
            return 0
        session = (pane.get("agent_session") or {}).get("value")
        pin = build_pin(
            turns, ref, name, folder, source, pane.get("agent"),
            session if source == "claude" else None, now,
        )
        store.save(pin)
    herdr.open_pane(
        "pin", "split", target_pane=pane_id, direction="right",
        env={"HERDR_STEPS_PIN": pin.id}, focus=False,
    )
    return 0


def cmd_pin(env, show_message, run_viewer_fn) -> int:
    store = PinStore(Path(env["HERDR_PLUGIN_STATE_DIR"]))
    pin = store.load(env.get("HERDR_STEPS_PIN") or "")
    if pin is None:
        show_message("That pin no longer exists")
        return 0

    from steps.viewer import ViewerState

    state = ViewerState(pin)
    run_viewer_fn(state, lambda: store.save(state.pin))
    return 0


def config_path(env, home: Path) -> Path:
    if env.get("HERDR_CONFIG_PATH"):
        return Path(env["HERDR_CONFIG_PATH"])
    return home / ".config" / "herdr" / "config.toml"


def cmd_setup(env, reload_config, now: datetime) -> int:
    from steps.keybinding import KEY, apply_binding

    path = config_path(env, Path.home())
    try:
        status = apply_binding(path, now)
    except ValueError as e:
        print(f"Couldn't read {path}: {e}")
        return 1
    if status == "already":
        print(f"{KEY} is already set up in {path}. Nothing changed.")
        return 0
    if status.startswith("conflict:"):
        print(f"{KEY} is already used by '{status.split(':', 1)[1]}' in {path}.")
        print("Nothing changed. Free that key or bind local.steps.mark yourself.")
        return 1
    print(f"Added {KEY} → pin agent steps to {path} (backup saved next to it).")
    try:
        reload_config()
        print("herdr reloaded its config. Press prefix+m in an agent pane to try it.")
    except Exception as e:  # reload is a convenience; the edit already worked
        print(f"Couldn't reload herdr's config ({e}). Run: herdr server reload-config")
    return 0


def _reload_config() -> None:
    import subprocess

    herdr = HerdrCli()
    proc = subprocess.run([herdr.bin, "server", "reload-config"],
                          capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    env = os.environ
    herdr = HerdrCli()
    if command == "mark":
        return cmd_mark(env, herdr)
    if command == "picker":
        from steps.picker import CursesPickerUI

        return cmd_picker(env, herdr, Path.home(), CursesPickerUI(), datetime.now())
    if command == "pin":
        from steps.picker import CursesPickerUI
        from steps.viewer import run_viewer

        return cmd_pin(env, CursesPickerUI().message, run_viewer)
    if command == "setup":
        return cmd_setup(env, _reload_config, datetime.now())
    print("usage: python3 -m steps mark|picker|pin|setup", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
