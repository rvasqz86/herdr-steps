# herdr-steps

Pin an agent's instructions beside the live agent in [herdr](https://herdr.dev).

When an agent gives you a list of steps and the conversation moves on, press
`prefix+m` in that agent's pane:

1. A popup lists the conversation, newest first. Your own messages are
   highlighted. `/` searches, `↑↓` move, `Enter` picks, `Esc` closes. Pins you
   made earlier in this project folder are listed at the top.
2. Pick where the instructions started. If you pick an agent reply, the pin
   starts at your question just before it. Name the pin (`Enter` keeps the
   suggested name).
3. A split opens on the right with a frozen copy of that part of the
   conversation. Step lines (numbered or bulleted) get checkboxes. Click one,
   or move with `↑↓` and press `Space`. `q` closes it. Your ticks are saved.

The agent keeps running on the left the whole time.

## Install

On any Linux or macOS machine with herdr:

```bash
herdr plugin install rvasqz86/herdr-steps
herdr plugin list            # shows the folder it was installed to
cd <that folder> && python3 -m steps setup
```

Get later changes with `herdr plugin update local.steps`.

For development, link a checkout instead:
`herdr plugin link ~/development/herdr-steps`.

`setup` adds this to your herdr config (`$HERDR_CONFIG_PATH` or
`~/.config/herdr/config.toml`), after saving a backup next to it, and reloads
herdr's config:

```toml
[[keys.command]]
key = "prefix+m"
type = "plugin_action"
command = "local.steps.mark"
description = "pin agent steps"
```

It changes nothing if the binding is already there, and refuses if
`prefix+m` is used by something else.

Needs Python 3.11+ (standard library only) as `python3` on herdr's PATH.
Linux and macOS. On a Mac, Apple's built-in `python3` is too old; install a
newer one (for example `brew install python`).

## Where history comes from

- **Claude Code:** its own session record in `~/.claude/projects/`, read-only.
  This covers the whole session, even though Claude Code's full-screen mode
  leaves herdr with no scrollback.
- **Everything else (for now):** herdr's scrollback for the pane, shown line
  by line.

pi, omp, copilot and cursor readers are planned next.

## Where pins live

`$HERDR_PLUGIN_STATE_DIR/pins/<id>.json` (see `herdr plugin config-dir
local.steps`). Pins belong to the project folder of the pane they came from,
so they survive Claude's `/clear` and herdr restarts.

## Development

```bash
python3 -m unittest
```

## License

MIT. See `LICENSE`.
