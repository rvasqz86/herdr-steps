import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from steps import __main__ as main
from steps.model import Turn
from steps.picker import PickerState, rel_time
from steps.pins import PinStore, build_pin

TURNS = [
    Turn("user", "fix the test", "2026-11-13T09:00:00Z"),
    Turn("agent", "Fixed it.", "2026-11-13T09:01:00Z"),
    Turn("user", "how do I get myapp on Cloudflare?", "2026-11-13T09:30:00Z"),
    Turn("tool", "Bash: npm run build", "2026-11-13T09:31:00Z"),
    Turn("agent", "You'll need an account.\n1. Create", "2026-11-13T09:32:00Z"),
]
NOW = datetime(2026, 11, 13, 10, 0, 0)


def a_pin(folder="/p"):
    return build_pin(TURNS, 2, "CF setup", folder, "claude", "claude", "s", NOW)


class PickerStateTest(unittest.TestCase):
    def test_rows_pins_first_then_newest_turns(self):
        s = PickerState(TURNS, [a_pin()])
        self.assertEqual([r.kind for r in s.rows][:2], ["pin", "turn"])
        self.assertEqual(s.rows[0].label, "★ CF setup · 0/1")
        self.assertEqual(s.rows[1].ref, 4)
        self.assertEqual(s.rows[-1].ref, 0)

    def test_user_rows_flagged(self):
        s = PickerState(TURNS, [])
        flags = {r.ref: r.is_user for r in s.rows}
        self.assertEqual(flags, {4: False, 2: True, 1: False, 0: True})

    def test_tool_turns_hidden(self):
        self.assertNotIn(3, [r.ref for r in PickerState(TURNS, []).rows])

    def test_search_filters_case_insensitive(self):
        s = PickerState(TURNS, [])
        s.move(2)
        s.set_query("cloudflare")
        self.assertEqual([r.ref for r in s.visible], [2])
        self.assertEqual(s.selected(), ("turn", 2))

    def test_move_clamps(self):
        s = PickerState(TURNS, [])
        s.move(-5)
        self.assertEqual(s.selected(), ("turn", 4))
        s.move(99)
        self.assertEqual(s.selected(), ("turn", 0))

    def test_selected_pin(self):
        p = a_pin()
        self.assertEqual(PickerState(TURNS, [p]).selected(), ("pin", p))

    def test_empty_state_selected_none(self):
        s = PickerState(TURNS, [])
        s.set_query("zzz")
        self.assertIsNone(s.selected())
        self.assertIsNone(PickerState([], []).selected())


class RelTimeTest(unittest.TestCase):
    def test_rel_time(self):
        now = datetime(2026, 11, 13, 10, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(rel_time("2026-11-13T09:48:00Z", now), "12m ago")
        self.assertEqual(rel_time("2026-11-13T07:00:00Z", now), "3h ago")
        self.assertEqual(rel_time("2026-11-11T10:00:00Z", now), "2d ago")
        self.assertEqual(rel_time("2026-11-13T09:59:50Z", now), "now")
        self.assertEqual(rel_time(None, now), "")
        self.assertEqual(rel_time("garbage", now), "")


class FakeHerdr:
    def __init__(self, pane, scrollback=""):
        self.pane = pane
        self.scrollback = scrollback
        self.opened = []

    def pane_get(self, pane_id):
        return self.pane

    def pane_read(self, pane_id, lines=2000):
        return self.scrollback

    def open_pane(self, *args, **kwargs):
        self.opened.append((args, kwargs))


class FakeUI:
    def __init__(self, choice=None, name="My pin"):
        self.choice = choice
        self.name = name
        self.messages = []
        self.default_name = None

    def message(self, text):
        self.messages.append(text)

    def pick(self, state):
        if self.choice is None:
            return None
        return self.choice(state)

    def ask_name(self, default):
        self.default_name = default
        return self.name


class MainTest(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp())
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state)
        self.addCleanup(shutil.rmtree, self.home)
        self.pane = {"pane_id": "w1:p1", "cwd": "/p", "agent": "cursor"}
        self.env = {"HERDR_STEPS_SOURCE_PANE": "w1:p1", "HERDR_PLUGIN_STATE_DIR": str(self.state)}

    def test_mark_without_focused_pane_exits_1(self):
        herdr = FakeHerdr(self.pane)
        self.assertEqual(main.cmd_mark({"HERDR_PLUGIN_CONTEXT_JSON": "{}"}, herdr), 1)
        self.assertEqual(herdr.opened, [])

    def test_mark_opens_popup_for_focused_pane(self):
        herdr = FakeHerdr(self.pane)
        env = {"HERDR_PLUGIN_CONTEXT_JSON": json.dumps({"focused_pane_id": "w1:p1"})}
        self.assertEqual(main.cmd_mark(env, herdr), 0)
        args, kwargs = herdr.opened[0]
        self.assertEqual(args, ("picker", "popup"))
        self.assertEqual(kwargs["env"], {"HERDR_STEPS_SOURCE_PANE": "w1:p1"})
        self.assertEqual((kwargs["width"], kwargs["height"]), ("80%", "70%"))

    def test_mark_ui_busy_message(self):
        from steps.herdr import HerdrError

        class Busy(FakeHerdr):
            def open_pane(self, *a, **k):
                raise HerdrError("plugin pane open failed: ui_busy")

        env = {"HERDR_PLUGIN_CONTEXT_JSON": json.dumps({"focused_pane_id": "w1:p1"})}
        self.assertEqual(main.cmd_mark(env, Busy(self.pane)), 1)

    def test_picker_nothing_to_pin(self):
        ui = FakeUI()
        rc = main.cmd_picker(self.env, FakeHerdr(self.pane, ""), self.home, ui, NOW)
        self.assertEqual(rc, 0)
        self.assertEqual(ui.messages, ["Nothing to pin in this pane yet"])

    def test_picker_turn_saves_pin_and_opens_split(self):
        herdr = FakeHerdr(self.pane, "Then:\n1. Create\n2. Connect\n")
        ui = FakeUI(choice=lambda s: ("turn", 0))
        self.assertEqual(main.cmd_picker(self.env, herdr, self.home, ui, NOW), 0)
        pins = PinStore(self.state).list_for_folder("/p")
        self.assertEqual([p.name for p in pins], ["My pin"])
        self.assertEqual(ui.default_name, "Then:")
        args, kwargs = herdr.opened[0]
        self.assertEqual(args, ("pin", "split"))
        self.assertEqual(kwargs["target_pane"], "w1:p1")
        self.assertEqual(kwargs["direction"], "right")
        self.assertEqual(kwargs["env"], {"HERDR_STEPS_PIN": pins[0].id})
        self.assertFalse(kwargs["focus"])

    def test_picker_existing_pin_reopens(self):
        p = a_pin()
        PinStore(self.state).save(p)
        herdr = FakeHerdr(self.pane, "")
        ui = FakeUI(choice=lambda s: s.selected())
        self.assertEqual(main.cmd_picker(self.env, herdr, self.home, ui, NOW), 0)
        self.assertEqual(herdr.opened[0][1]["env"], {"HERDR_STEPS_PIN": p.id})

    def test_picker_cancel_name_saves_nothing(self):
        herdr = FakeHerdr(self.pane, "a line\n")
        ui = FakeUI(choice=lambda s: ("turn", 0), name=None)
        self.assertEqual(main.cmd_picker(self.env, herdr, self.home, ui, NOW), 0)
        self.assertEqual(PinStore(self.state).list_for_folder("/p"), [])
        self.assertEqual(herdr.opened, [])


class SplitFailureTest(MainTest):
    def test_picker_split_open_failure_shows_message(self):
        from steps.herdr import HerdrError

        class Failing(FakeHerdr):
            def open_pane(self, *a, **k):
                raise HerdrError("plugin pane open failed: pane not found")

        ui = FakeUI(choice=lambda s: ("turn", 0))
        rc = main.cmd_picker(self.env, Failing(self.pane, "1. a\n"), self.home, ui, NOW)
        self.assertEqual(rc, 1)
        self.assertEqual(len(PinStore(self.state).list_for_folder("/p")), 1)
        self.assertIn("Saved pin 'My pin' but couldn't open it", ui.messages[0])
        self.assertIn("prefix+m", ui.messages[0])
