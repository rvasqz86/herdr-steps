# herdr-steps: pin an agent's instructions beside the live agent

Status: draft for approval · 2026-11-11

## Why

When working with a coding agent in herdr, the agent often hands over a set of
manual steps (example: "set up a Cloudflare Pages project for myapp"). The
conversation keeps going, and finding the *start* of those instructions means
scrolling back through a long history, then losing the place again while
working through them.

The user wants two things at once:

1. **Get back** to where the instructions started without scrolling.
2. **Keep them on screen** while working, with the live agent still running
   alongside.

Seeing the *start* of the instructions matters: the user's own question and
the agent's intro (prerequisites, context) are part of what they need, not just
the extracted step lines.

## What it is

A herdr plugin (not a change to herdr itself), so herdr can keep updating
normally via `herdr update` and the plugin keeps working.

### The flow

1. In an agent pane, the user presses `prefix+m`.
2. A popup lists that agent session's conversation turns, newest first:
   the user's typed prompts and the agent's visible text replies. User prompts
   are visually distinct. Tool calls, tool results (which Claude records as
   `type: "user"`), thinking, and system/meta records are **not** rows.
   Each row shows a relative time and the first line of the message. `/`
   searches; arrows move; Enter picks; Esc cancels. *(my call)*
3. On pick, the user is offered a name for the pin (default: the picked
   message's first line, trimmed). Enter accepts.
4. A **split pane** opens beside the agent pane showing a **frozen copy** of
   the conversation captured at that moment. It always **starts at a user
   prompt**: if the user picked an agent message, the pin snaps back to the
   user prompt immediately before it, so the question and the agent's intro
   are always visible. *(my call)* It contains user prompts and the agent's
   visible text only. Each tool call appears as one dim summary line (e.g.
   `⏺ Ran npm run build`), with no tool output and no thinking. *(my call)*
   *(Builder's call: how far the frozen range extends — see Left to the builder.)*
5. Lines **in the agent's visible text** that look like steps (numbered
   `1.`/`1)` or bulleted `-`/`*`/`•` items) render with a checkbox. Click or
   Space toggles. Other text is plain. Continuation lines of a step stay
   attached to it visually. Tool summary lines and user prompts never get
   checkboxes.
6. The pin's header shows its name and progress, e.g. `★ Cloudflare setup · 2/5`.
7. The side pane scrolls independently. `q` closes it. Ticks and the frozen
   text persist; pressing `prefix+m` again in the same agent pane offers
   existing pins at the top of the picker so the user can reopen one as they
   left it.

Reference mockups (approved), in `mockups/` next to this file:
`hybrid-v1.html` (frozen view with checkboxes, live agent on the left, frozen
pin on the right, header `★ <name> · done/total`) and `plugin-flow-v1.html`
(the "where do the instructions start?" picker popup, then the split). They
are illustrative of layout and feel; where they and this text differ, this
text wins (e.g. the picker excludes tool rows like "Ran npm run build").

### Where history comes from

herdr's own scrollback is **not** a usable source for Claude Code: Claude Code
draws full-screen in herdr, so herdr holds only the current screen (verified:
the myapp Claude pane reports `max_offset_from_bottom: 0` and `pane read
--source recent` returns ~22 lines). The plugin therefore reads each agent's
own session record, found via the pane's `agent_session` from
`herdr pane list`/`pane get` (or, where herdr doesn't provide a session id, the
most recent session for the pane's cwd).

| Agent (herdr id) | Session record observed on this machine |
|---|---|
| `claude` | `~/.claude/projects/<cwd-slug>/<session-id>.jsonl` — records with `type: "user"` / `"assistant"`, `message.content` a list |
| `pi` | `~/.pi/agent/sessions/<cwd-slug>/<ts>_<id>.jsonl` — `type: "message"`, `message.role` user/assistant |
| omp | `~/.omp/agent/sessions/<cwd-slug>/<ts>_<id>.jsonl` — same shape as pi |
| `github-copilot` | `~/.copilot/session-state/<id>/events.jsonl` — event stream (`session.start`, …); message event names to be confirmed |
| `cursor` | `~/.cursor/chats/<hash>/<id>/store.db` — SQLite with `blobs`, `meta` tables; format to be investigated |

Order of support: **Claude Code first** (it's the trigger case), then pi and
omp (shared format), then copilot, then cursor.

**Phasing (my call):** the first plan covers Claude Code + the scrollback
fallback + the full pin UI. pi/omp readers are a second phase. copilot and
cursor each start with a short format investigation before their reader. The
reader interface (session → ordered list of `{role, text, tool_summary,
timestamp}` turns) should be defined in phase one so later readers plug in.

**Fallback** for any agent without a working reader, or when a reader fails:
use herdr's scrollback (`herdr pane read <pane> --source recent-unwrapped
--lines N`), presenting lines instead of turns. Cursor already has substantial
herdr scrollback (~3,100 rows observed), so the fallback is useful there even
before its reader exists. If neither source yields anything, show a clear
message rather than an empty picker.

Readers must open session files **read-only** and tolerate partial last lines
(the agent may be writing). A format change in an agent should degrade to the
fallback, never crash the plugin.

## Goals

- One keystroke to get from "I need those steps" to having them on screen.
- The start of the instructions (user's question + agent intro) is always
  visible in the pin.
- Live agent keeps running and stays fully usable on the other side.
- Ticks survive closing the pane and restarting herdr.
- Works for Claude Code on day one; pi, omp, copilot, cursor follow.

## Non-goals

- Modifying herdr. No fork, no PR. (The user is not a herdr maintainer or
  approved contributor; upstream proposals go via GitHub Discussions, later
  and optionally.)
- Scrolling the agent pane back to the source ("jump to source"). herdr has
  no API to scroll another pane to a position; the frozen view replaces it.
- Letting the agent read or edit pins.
- Live-updating pins as the agent keeps talking. Pins are frozen copies.
- Syncing pins across machines.

## Anti-goals (would make it a failure even if it "works")

- Breaking or interfering with `herdr update`.
- Stealing keys or focus from the agent pane outside of `prefix+m` and the
  plugin's own pane/popup.
- Showing the wrong conversation (e.g. another pane's session) without making
  that obvious.
- Writing to, locking, or corrupting an agent's session files.

## Constraints

- herdr plugin v1: manifest `herdr-plugin.toml`, actions, panes
  (`popup`/`split`/…), keybinding via `[[keys.command]]` with
  `type = "plugin_action"`. Plugin talks to herdr only through
  `$HERDR_BIN_PATH` CLI / socket. Context in `HERDR_PLUGIN_CONTEXT_JSON`.
  Durable state in `HERDR_PLUGIN_STATE_DIR` (plugin-owned). Docs:
  `docs/next/website/src/content/docs/plugins.mdx` in the herdr repo.
- A popup returns `ui_busy` if Copy mode/Settings/another modal is open;
  handle with a short message.
- Installed herdr is now 0.9.5 (plugins supported, including `split` and
  `popup` panes). Set `min_herdr_version` no higher than 0.9.0.
- `prefix+m` is currently unbound in defaults and the user's config.
- Linux is the only platform that matters now (`platforms = ["linux"]`;
  macOS likely free, not a goal).

## Decisions made (my calls, user can override)

- **Separate repo** at `~/development/herdr-steps`, linked with
  `herdr plugin link`.
- **Python 3 stdlib only** (Python 3.13 present; `curses`, `json`,
  `sqlite3` available). No pip dependencies.
- **Plugin name/id:** `herdr-steps` / `local.steps` (rename freely).
- **Key:** `prefix+m`. **Setup adds the binding for the user** (user
  decision): append one `[[keys.command]]` entry (`type = "plugin_action"`)
  to `~/.config/herdr/config.toml`. Back the file up first, don't add a
  duplicate if one already exists, refuse if `prefix+m` is already bound to
  something else, and leave every other line untouched.
- **Pins belong to the project folder** (the agent pane's cwd), not to a
  session id or herdr pane. Claude's `/clear` and some resume flows start a
  new session id, and the scrollback fallback has no session at all; keying
  by folder keeps "reopen it as you left it" working through both. The
  picker lists existing pins for that folder at the top (most recent first),
  and each pin also records its source agent and session id for display.
- **Step detection** is a simple line heuristic (numbered or bulleted lines);
  no AI parsing.

## Left to the builder

- Popup + split coordination: e.g. the action opens a popup picker which,
  on pick, writes the pin to state and opens the split pane entrypoint with
  the pin id; or a single split-pane program that shows the picker inline
  first. Choose what herdr's plugin API makes reliable.
- Exact end of the frozen range (end of the picked turn's agent reply vs.
  a fixed number of following turns vs. user-adjustable).
- Rendering of agent markdown (keep it plain text with light styling).
- State file layout and pin ids.
- How the side pane width is chosen (sensible default, user can resize as a
  normal herdr pane).
- Mouse support details in curses (click to tick is required).
- Testing approach: unit tests for each session reader against small
  synthetic fixtures and for step detection; manual smoke test in a real
  herdr session against the myapp Claude pane.
