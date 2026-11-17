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

Works on Linux and macOS. On each machine:

1. **Check herdr.** You need herdr 0.9.0 or newer (plugins arrived in 0.9.0):

   ```bash
   herdr --version
   ```

   If it's older, run `herdr update` (or `brew upgrade herdr` if you installed
   it with Homebrew).

2. **Check Python.** You need Python 3.11 or newer as `python3`:

   ```bash
   python3 --version
   ```

   On a Mac, Apple's built-in `python3` is too old. Install a newer one with
   `brew install python`, open a new terminal, and check again.

3. **Install the plugin:**

   ```bash
   herdr plugin install rvasqz86/herdr-steps
   ```

   herdr asks you to confirm, then downloads it to
   `~/.config/herdr/plugins/github/local.steps-<code>`.

4. **Add the shortcut:**

   ```bash
   cd ~/.config/herdr/plugins/github/local.steps-* && python3 -m steps setup
   ```

5. **Try it.** In a pane running an agent, press the herdr prefix, then `m`.
   The prefix is `Ctrl+B` unless you changed `prefix` under `[keys]` in your
   herdr config.

Get later changes with `herdr plugin update local.steps`.

For development, link a checkout instead of installing:
`herdr plugin link ~/development/herdr-steps`, then run step 4 from that
folder.

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

The plugin uses only Python's standard library; nothing else to install.

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
