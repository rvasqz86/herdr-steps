# herdr-steps Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A herdr plugin where `prefix+m` in a Claude Code pane opens a picker of conversation turns, and picking one opens a frozen, tickable copy of those instructions in a split beside the live agent.

**Architecture:** Pure-Python, stdlib-only package `steps/`. Data layer (session readers → `Turn` list → `Pin` with classified lines → JSON store) is fully unit-tested without herdr or curses. A thin `herdr.py` wraps `$HERDR_BIN_PATH` CLI calls. Two curses UIs (picker, pin viewer) are thin shells over pure state classes that are unit-tested. The plugin action opens the picker as a `popup` (floating box, 80% × 70%); the picker saves a pin and opens the pin viewer as a `split` to the right of the agent pane, then exits.

**Tech Stack:** Python 3.13 stdlib (`json`, `curses`, `tomllib`, `dataclasses`, `subprocess`, `unittest`). herdr plugin v1 manifest. Tests run with `python3 -m unittest`.

**Spec:** `docs/superpowers/specs/2026-11-11-herdr-steps-design.md` (read it; mockups in `docs/superpowers/specs/mockups/`).

## Global Constraints

- Repo: `~/development/herdr-steps` (own git repo). Plugin id `local.steps`, name `herdr-steps`.
- No pip dependencies. Python 3 stdlib only.
- `min_herdr_version = "0.9.0"`; `platforms = ["linux"]`.
- Installed herdr 0.9.5 (latest stable) supports `--placement popup` (its `--help` omits it, but the parser accepts it: `src/cli/plugin.rs:872` at v0.9.5). Picker uses `popup` with `--width 80% --height 70%`. A popup has no `HERDR_PANE_ID`; the source pane is passed via `--env`. Opening returns `ui_busy` while copy mode/settings/a modal is open: `mark` reports that in plain words.
- Agent session files are opened read-only and never written, locked, or moved.
- Never crash on bad input: a reader failure falls back to scrollback; empty sources show a message.
- Key: `prefix+m`, bound by setup in `~/.config/herdr/config.toml` (or `$HERDR_CONFIG_PATH`): back up first, no duplicate, refuse if `prefix+m` is bound to something else, leave other lines untouched.
- Plugin calls herdr only via `$HERDR_BIN_PATH` (fallback `herdr`).
- Pins keyed by project folder (agent pane cwd), stored under `$HERDR_PLUGIN_STATE_DIR`.

## Review Focus

1. A Claude session file whose last line is half-written (agent mid-write) → reader ignores that line, returns the rest. (Task 2 test)
2. Claude user records that aren't typed prompts (tool results, `isMeta`, `<command-name>`/`<local-command-stdout>`/`<system-reminder>` wrappers, sidechain records) → never appear as user turns. (Task 2 test)
3. Tool output or user prompts containing `1.`/`-` lines → never get checkboxes. (Task 3 test)
4. `prefix+m` already bound in `[keys]` (e.g. `foo = ["prefix+m"]`) or the config file missing → setup refuses or creates cleanly, never corrupts. (Task 5 test)
5. Picker opened on a pane with no agent session and no scrollback → message "Nothing to pin in this pane yet", exits 0. (Task 6 test)

---

## File Structure

```
herdr-steps/
  herdr-plugin.toml          manifest: action "mark", panes "picker", "pin"
  README.md                  install + usage
  steps/__init__.py
  steps/__main__.py          CLI dispatch: mark | picker | pin | setup
  steps/model.py             Turn, PinLine, Pin dataclasses
  steps/sources/__init__.py  load_turns()
  steps/sources/claude.py    Claude JSONL reader + session file lookup
  steps/sources/scrollback.py herdr scrollback → line turns
  steps/pins.py              build_pin(), classify_lines(), PinStore
  steps/keybinding.py        ensure_binding() pure + apply_binding() I/O
  steps/herdr.py             HerdrCli wrapper
  steps/picker.py            PickerState (pure) + run_picker() curses
  steps/viewer.py            ViewerState (pure) + run_viewer() curses
  tests/test_*.py            one per module; fixtures in tests/fixtures/
```

---

### Task 1: Repo scaffold and data model

**Files:**
- Create: `herdr-plugin.toml`, `steps/__init__.py`, `steps/model.py`, `tests/__init__.py`, `tests/test_model.py`, `.gitignore` (`__pycache__/`)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Turn: role: str  # "user" | "agent" | "tool" | "line"; text: str; timestamp: str | None`
  - `@dataclass class PinLine: kind: str  # "user" | "text" | "tool" | "step" | "blank"; text: str; step_id: int | None = None`
  - `@dataclass class Pin: id: str; name: str; folder: str; source: str  # "claude" | "scrollback"; agent: str | None; session_id: str | None; created_at: str; lines: list[PinLine]; checked: set[int]` with `to_dict() -> dict` and `@classmethod from_dict(d) -> Pin` (`checked` serialized as sorted list), plus `@property progress -> tuple[int, int]` (checked count, total step count).

- [ ] **Step 1:** `git init` in `~/development/herdr-steps` (spec and mockups already present).
- [ ] **Step 2: Write failing tests** `tests/test_model.py`: `test_pin_roundtrip` (`Pin.from_dict(p.to_dict()) == p` with 2 step lines, `checked={1}`), `test_progress` (`(1, 2)`), `test_progress_no_steps` (`(0, 0)`).
- [ ] **Step 3:** Run `python3 -m unittest -v` → FAIL (import error).
- [ ] **Step 4:** Implement `steps/model.py`. Write the manifest:

```toml
id = "local.steps"
name = "herdr-steps"
version = "0.1.0"
min_herdr_version = "0.9.0"
description = "Pin an agent's instructions beside the live agent"
platforms = ["linux"]

[[actions]]
id = "mark"
title = "Pin agent steps"
contexts = ["pane"]
command = ["python3", "-m", "steps", "mark"]

[[panes]]
id = "picker"
title = "Pin steps"
placement = "popup"
width = "80%"
height = "70%"
command = ["python3", "-m", "steps", "picker"]

[[panes]]
id = "pin"
title = "Steps"
placement = "split"
command = ["python3", "-m", "steps", "pin"]
```

  Check `contexts` values against herdr's manifest validator (`herdr plugin link` errors on bad values); use `["workspace"]` if `"pane"` is rejected.
- [ ] **Step 5:** Run `python3 -m unittest -v` → PASS.
- [ ] **Step 6:** Commit `feat: scaffold herdr-steps plugin and data model` (include the spec + mockups in this first commit).

---

### Task 2: Claude Code session reader

**Files:**
- Create: `steps/sources/__init__.py` (empty for now), `steps/sources/claude.py`, `tests/test_claude.py`, `tests/fixtures/claude_basic.jsonl`

**Interfaces:**
- Consumes: `Turn`
- Produces:
  - `find_claude_session(session_id: str | None, cwd: str, home: Path) -> Path | None` — if `session_id`, glob `home/.claude/projects/*/{session_id}.jsonl`; else newest `*.jsonl` (by mtime) in `home/.claude/projects/<slug>/` where `slug = re.sub(r"[^A-Za-z0-9]", "-", cwd)`.
  - `read_claude_turns(path: Path) -> list[Turn]`

**Rules for `read_claude_turns`** (fixture must exercise every one):
- Skip lines that fail `json.loads` (partial last line).
- Skip records where `type` not in `("user","assistant")`, or `isSidechain` or `isMeta` is true.
- `user` with `message.content` a str → `Turn("user", text)` unless the stripped text starts with `<command-name>`, `<command-message>`, `<local-command-stdout>`, `<local-command-caveat>`, or `<system-reminder>` (skip). `content` a list → join `text` items; if the list contains only `tool_result` items, skip.
- `assistant`: for each content item in order: `text` → `Turn("agent", text)`; `tool_use` → `Turn("tool", summary)` with `summary = f"{name}: {first_line(input.get('description') or input.get('command') or input.get('file_path') or '')}"` truncated to 80 chars; `thinking` → skip.
- Consecutive `agent` turns with no turn between them merge into one (newline-joined).
- `timestamp` copied from the record.

- [ ] **Step 1: Write fixture** `claude_basic.jsonl` (≈12 lines): a summary record, an `isMeta` user, a `<command-name>` user, a typed user prompt "how do I get myapp on cloudflare?", assistant thinking, assistant text with a numbered list, assistant tool_use Bash, user tool_result, assistant text, a sidechain assistant, a second typed user prompt as a list content, and a truncated final line `{"type":"assist`.
- [ ] **Step 2: Write failing tests:** `test_reads_turns_in_order` (exact list of `(role, text-prefix)` tuples expected for the fixture), `test_skips_partial_last_line`, `test_tool_summary` (`"Bash: npm run build"`), `test_find_by_session_id`, `test_find_newest_by_cwd` (tmp dir with two files, different mtimes), `test_find_missing_returns_none`.
- [ ] **Step 3:** Run `python3 -m unittest tests.test_claude -v` → FAIL.
- [ ] **Step 4:** Implement `steps/sources/claude.py`.
- [ ] **Step 5:** Run → PASS. Then run against the real file once as a smoke check: `python3 -c "from steps.sources.claude import *; from pathlib import Path; t=read_claude_turns(find_claude_session('d26960d3-9c20-4da5-96de-42a7d4ad3f35','',Path.home())); print(len(t), [x.role for x in t][:20])"` → non-zero count, roles include `user` and `agent`.
- [ ] **Step 6:** Commit `feat: read claude code session turns`.

---

### Task 3: Pin building and step detection

**Files:**
- Create: `steps/pins.py`, `tests/test_pins.py`

**Interfaces:**
- Consumes: `Turn`, `PinLine`, `Pin`
- Produces:
  - `snap_to_user(turns: list[Turn], index: int) -> int` — nearest `user` turn at or before `index`; if none, `index`. For `line` turns returns `index`.
  - `pin_range(turns: list[Turn], start: int) -> list[Turn]` — for chat turns: from `start` through the turn before the next `user` turn after `start` (or end). For `line` turns: `turns[start:start+200]`.
  - `classify_lines(turns: list[Turn]) -> list[PinLine]` — `user` → one `PinLine("user", "> " + first line)` plus remaining lines as `"user"`; `tool` → `PinLine("tool", "⏺ " + text)`; `agent`/`line` text split on `\n`: a line matching `^\s*(\d+[.)]|[-*•])\s+\S` → `"step"` with incrementing `step_id` from 0; an indented non-empty line directly after a step (more leading spaces than the step marker) → `"text"` attached (same step_id for display only, not counted); empty → `"blank"`; else `"text"`. A blank `PinLine` separates turns.
  - `build_pin(turns, picked: int, name: str, folder: str, source: str, agent: str | None, session_id: str | None, now: datetime) -> Pin` — snaps, ranges, classifies; `id = now.strftime("%Y%m%d-%H%M%S")`.
  - `default_name(turn: Turn) -> str` — first line, stripped, max 40 chars.
  - `class PinStore(state_dir: Path)`: `save(pin)`, `load(pin_id) -> Pin | None`, `list_for_folder(folder) -> list[Pin]` (newest first), `toggle(pin_id, step_id) -> Pin`. Files: `state_dir/pins/<id>.json`, written atomically (tmp + `os.replace`).

- [ ] **Step 1: Write failing tests:** `test_snap_from_agent_to_user`, `test_snap_no_user_before`, `test_range_stops_at_next_user`, `test_steps_numbered_and_bullets` (input "Then:\n1. Create\n2) Connect\n- Add vars\n* Build\n• Domain" → five steps, ids 0–4), `test_user_and_tool_never_steps` (user turn "1. do x", tool turn "Bash: - x" → kinds `user`, `tool`), `test_continuation_line_not_counted` ("3. Add env vars:\n   DATABASE_URL" → 1 step), `test_build_pin_starts_at_question` (pick agent index → `pin.lines[0].kind == "user"`), `test_store_roundtrip_and_toggle`, `test_list_for_folder_filters_and_sorts`.
- [ ] **Step 2:** Run `python3 -m unittest tests.test_pins -v` → FAIL.
- [ ] **Step 3:** Implement `steps/pins.py`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: build pins with step checkboxes and store them`.

---

### Task 4: herdr CLI wrapper, scrollback fallback, and source selection

**Files:**
- Create: `steps/herdr.py`, `steps/sources/scrollback.py`, `tests/test_sources.py`
- Modify: `steps/sources/__init__.py`

**Interfaces:**
- Produces:
  - `class HerdrCli(bin_path: str | None = None, run=subprocess.run)` — `bin = bin_path or os.environ.get("HERDR_BIN_PATH") or "herdr"`. Methods: `pane_get(pane_id) -> dict` (returns `result.pane` from `herdr pane get <id>` JSON), `pane_read(pane_id, lines=2000) -> str` (`pane read <id> --source recent-unwrapped --lines N`), `open_pane(entrypoint: str, placement: str, target_pane: str | None = None, direction: str | None = None, width: str | None = None, height: str | None = None, env: dict[str,str] | None = None, focus: bool = True) -> None` (`plugin pane open --plugin local.steps ...`, one `--env K=V` each, `--focus`/`--no-focus`). Raise `HerdrError(msg)` on non-zero exit, with stderr.
  - `scrollback_turns(text: str) -> list[Turn]` — each non-blank line → `Turn("line", line.rstrip(), None)`.
  - `load_turns(pane: dict, herdr: HerdrCli, home: Path) -> tuple[list[Turn], str]` — returns `(turns, source)`. If `pane.get("agent") == "claude"`: try `find_claude_session(pane.get("agent_session", {}).get("value"), pane["cwd"], home)` + `read_claude_turns`; on any exception or empty result fall through. Fallback: `scrollback_turns(herdr.pane_read(pane["pane_id"]))`, source `"scrollback"`. Returns `([], "none")` if both empty.

- [ ] **Step 1: Write failing tests** with a fake `run` recording argv and returning canned stdout: `test_pane_get_parses_result`, `test_open_pane_argv` (asserts exact argv incl. `--placement split --target-pane w1:p1 --direction right --env HERDR_STEPS_PIN=abc`), `test_error_on_nonzero`, `test_load_turns_claude` (tmp home with fixture), `test_load_turns_falls_back_when_claude_file_missing`, `test_load_turns_falls_back_for_other_agents`, `test_load_turns_none`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: herdr cli wrapper and scrollback fallback`.

---

### Task 5: Keybinding setup

**Files:**
- Create: `steps/keybinding.py`, `tests/test_keybinding.py`

**Interfaces:**
- Produces:
  - `BLOCK = '\n# herdr-steps: pin agent instructions\n[[keys.command]]\nkey = "prefix+m"\ntype = "plugin_action"\ncommand = "local.steps.mark"\ndescription = "pin agent steps"\n'`
  - `ensure_binding(config_text: str) -> tuple[str, str]` — returns `(new_text, status)`, status one of `"added"`, `"already"`, `"conflict:<where>"`. Parse with `tomllib`; scan every value under `[keys]` (strings and lists of strings) and every `keys.command[*].key` for `"prefix+m"`. Ours = a `keys.command` entry with `command == "local.steps.mark"` → `"already"`. Other match → `"conflict:<key name>"`, text unchanged. Else append `BLOCK` (ensuring the file ends with `\n` first). Invalid TOML → raise `ValueError`.
  - `apply_binding(config_path: Path, now: datetime) -> str` — missing file → write `BLOCK.lstrip()` and return `"added"`. Else on `"added"` copy original to `config.toml.bak-herdr-steps-<YYYYmmdd-HHMMSS>` before writing. Return status. Path from `$HERDR_CONFIG_PATH` else `~/.config/herdr/config.toml` (resolved by the caller in Task 7).

- [ ] **Step 1: Write failing tests:** `test_adds_to_existing_config` (input has `[keys]` + an existing `[[keys.command]]`; output equals input + `BLOCK`, and `tomllib` parses it), `test_idempotent`, `test_conflict_in_keys_table` (`[keys]\nfoo = ["prefix+m"]`), `test_conflict_in_command_entry`, `test_invalid_toml_raises`, `test_apply_creates_backup`, `test_apply_missing_file_creates`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: add prefix+m binding setup`.

---

### Task 6: Picker (state + curses UI) and the `mark`/`picker` entrypoints

**Files:**
- Create: `steps/picker.py`, `steps/__main__.py`, `tests/test_picker.py`

**Interfaces:**
- Consumes: `load_turns`, `HerdrCli`, `PinStore`, `build_pin`, `default_name`
- Produces:
  - `class PickerState(turns: list[Turn], pins: list[Pin])` — rows: existing pins first (label `★ <name> · d/t`), then turns newest first, excluding `tool` turns; `user` rows flagged for highlight. Methods: `move(delta)`, `set_query(q)` (case-insensitive substring filter over row text; selection resets to first row), `selected() -> ("pin", Pin) | ("turn", int) | None` (turn index into the original `turns` list).
  - `run_picker(stdscr, state) -> selection | None`, then a name prompt (prefilled `default_name`, Enter accepts, Esc cancels). Keys: ↑/↓/k/j, PgUp/PgDn, `/` search, Enter, Esc/q. Header: `★ Where do the instructions start?` and a help line as in `mockups/plugin-flow-v1.html`. Relative time column from `timestamp`.
  - `__main__` subcommands:
    - `mark`: parse `HERDR_PLUGIN_CONTEXT_JSON`; `pane = focused_pane_id`; if missing, print error and exit 1. `open_pane("picker", "popup", width="80%", height="70%", env={"HERDR_STEPS_SOURCE_PANE": pane})`; a `HerdrError` mentioning `ui_busy` → print "Close copy mode or the open menu first" and exit 1.
    - `picker`: `pane = herdr.pane_get($HERDR_STEPS_SOURCE_PANE)`; `turns, source = load_turns(...)`; if no turns and no pins → show "Nothing to pin in this pane yet" until a key, exit 0. Run picker. On a turn: build + save pin. On a pin or new pin: `open_pane("pin", "split", target_pane=pane, direction="right", env={"HERDR_STEPS_PIN": pin.id}, focus=False)`. Exit (popup closes).

- [ ] **Step 1: Write failing tests** (pure state only): `test_rows_pins_first_then_newest_turns`, `test_tool_turns_hidden`, `test_search_filters_case_insensitive`, `test_selected_maps_to_original_index`, `test_empty_state_selected_none`; and for `__main__`: `test_mark_without_focused_pane_exits_1`, `test_picker_nothing_to_pin` (fake HerdrCli, `curses` UI function injected/stubbed).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: turn picker and mark action`.

---

### Task 7: Pin viewer, `pin` and `setup` entrypoints, README, live smoke test

**Files:**
- Create: `steps/viewer.py`, `tests/test_viewer.py`, `README.md`
- Modify: `steps/__main__.py`

**Interfaces:**
- Consumes: `PinStore`, `Pin`, `apply_binding`
- Produces:
  - `class ViewerState(pin: Pin)` — `cursor` over step lines only; `scroll`; `toggle_at_cursor() -> int | None` (step id); `toggle_row(row: int) -> int | None` (for mouse click on a rendered row; returns None on non-step rows); `header() -> str` = `f"★ {name} · {done}/{total}"`.
  - `run_viewer(stdscr, state, on_toggle)` — renders header, then lines: `user` in blue, `tool` dim, `step` as `[x]`/`[ ]` (green when checked), current step highlighted. Keys: ↑/↓/j/k move between steps, PgUp/PgDn/mouse wheel scroll, Space toggles, `q` quits. Mouse: `curses.mousemask(ALL_MOUSE_EVENTS)`, click on a step row toggles. `on_toggle` persists via `PinStore.toggle` immediately.
  - `__main__` `pin`: load `$HERDR_STEPS_PIN` from `PinStore(Path($HERDR_PLUGIN_STATE_DIR))`; missing → message and exit 0.
  - `__main__` `setup`: resolve config path, `apply_binding`, print status in plain words; on `"added"` run `herdr server reload-config` and print it; on `conflict` print which key and exit 1.

- [ ] **Step 1: Write failing tests:** `test_header_progress`, `test_cursor_skips_non_steps`, `test_toggle_at_cursor`, `test_toggle_row_non_step_none`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run `python3 -m unittest -v` (all) → PASS.
- [ ] **Step 5:** README: what it does, `herdr plugin link ~/development/herdr-steps`, `python3 -m steps setup`, usage, where pins live, Claude-only in phase one.
- [ ] **Step 6: Live smoke test** (record results in the commit body or a note):
  1. `herdr plugin link ~/development/herdr-steps` → linked without errors.
  2. `python3 -m steps setup` → "added"; config diff shows only the appended block; backup file exists; second run → "already".
  3. In the myapp Claude pane press `prefix+m` → popup picker lists turns; search `cloudflare` finds the question.
  4. Pick an agent message → split opens on the right starting with the user's question; the agent pane is still live and focused.
  5. Click and Space tick steps; `q`; `prefix+m` again → pin at top; reopen shows ticks kept.
  6. In a plain shell pane, `prefix+m` → scrollback lines listed (or the "nothing to pin" message on an empty shell).
  7. `herdr plugin log list --plugin local.steps` → no errors.
  If the split fails to open while the popup is active, switch to: picker writes the chosen pin id to `$HERDR_PLUGIN_STATE_DIR/pending` and exits; `mark` waits for the popup to close (poll up to 10 min for the file, checking every 0.3 s) and opens the split. Note the change in README.
- [ ] **Step 7:** Commit `feat: pin viewer, setup command, readme`.
