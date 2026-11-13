import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from steps.model import Turn
from steps.pins import (
    PinStore,
    build_pin,
    classify_lines,
    default_name,
    pin_range,
    snap_to_user,
)

CHAT = [
    Turn("user", "fix the test"),
    Turn("agent", "Fixed."),
    Turn("user", "how do I get myapp on cloudflare?"),
    Turn("agent", "You'll need an account. Then:\n1. Create\n2. Connect"),
    Turn("tool", "Bash: npm run build"),
    Turn("agent", "Build passed."),
    Turn("user", "ok, DNS?"),
    Turn("agent", "Add a CNAME."),
]
NOW = datetime(2026, 11, 13, 10, 0, 0)


def kinds(lines):
    return [l.kind for l in lines]


class SnapAndRangeTest(unittest.TestCase):
    def test_snap_from_agent_to_user(self):
        self.assertEqual(snap_to_user(CHAT, 5), 2)

    def test_snap_user_stays(self):
        self.assertEqual(snap_to_user(CHAT, 2), 2)

    def test_snap_no_user_before(self):
        turns = [Turn("agent", "a"), Turn("user", "b")]
        self.assertEqual(snap_to_user(turns, 0), 0)

    def test_snap_line_turns_unchanged(self):
        turns = [Turn("line", "a"), Turn("line", "b")]
        self.assertEqual(snap_to_user(turns, 1), 1)

    def test_range_stops_at_next_user(self):
        self.assertEqual(pin_range(CHAT, 2), CHAT[2:6])

    def test_range_to_end(self):
        self.assertEqual(pin_range(CHAT, 6), CHAT[6:])

    def test_range_line_turns_capped_at_200(self):
        turns = [Turn("line", str(i)) for i in range(500)]
        self.assertEqual(pin_range(turns, 10), turns[10:210])


class ClassifyTest(unittest.TestCase):
    def test_steps_numbered_and_bullets(self):
        lines = classify_lines(
            [Turn("agent", "Then:\n1. Create\n2) Connect\n- Add vars\n* Build\n• Domain")]
        )
        steps = [l for l in lines if l.kind == "step"]
        self.assertEqual([l.step_id for l in steps], [0, 1, 2, 3, 4])
        self.assertEqual(lines[0].kind, "text")

    def test_user_and_tool_never_steps(self):
        lines = classify_lines([Turn("user", "1. do x"), Turn("tool", "Bash: - x")])
        self.assertNotIn("step", kinds(lines))
        self.assertEqual(lines[0].text, "> 1. do x")
        self.assertIn("⏺ Bash: - x", [l.text for l in lines])

    def test_continuation_line_not_counted(self):
        lines = classify_lines([Turn("agent", "3. Add env vars:\n   DATABASE_URL")])
        self.assertEqual(kinds(lines), ["step", "text"])
        self.assertEqual(lines[1].step_id, 0)

    def test_unindented_line_after_step_is_plain(self):
        lines = classify_lines([Turn("agent", "1. one\nDone.")])
        self.assertEqual(lines[1].step_id, None)

    def test_blank_between_turns(self):
        lines = classify_lines([Turn("user", "q"), Turn("agent", "a")])
        self.assertEqual(kinds(lines), ["user", "blank", "text"])

    def test_scrollback_lines_can_be_steps(self):
        lines = classify_lines([Turn("line", "1. one"), Turn("line", "2. two")])
        self.assertEqual(kinds(lines), ["step", "step"])


class BuildPinTest(unittest.TestCase):
    def test_build_pin_starts_at_question(self):
        pin = build_pin(CHAT, 3, "CF", "/p", "claude", "claude", "s1", NOW)
        self.assertEqual(pin.lines[0].kind, "user")
        self.assertEqual(pin.lines[0].text, "> how do I get myapp on cloudflare?")
        self.assertEqual(pin.id, "20261113-100000")
        self.assertEqual(pin.progress, (0, 2))
        self.assertNotIn("Add a CNAME.", [l.text for l in pin.lines])

    def test_default_name(self):
        self.assertEqual(default_name(Turn("user", "  hello there\nmore")), "hello there")
        self.assertEqual(len(default_name(Turn("user", "x" * 99))), 40)


class PinStoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.store = PinStore(self.dir)

    def pin(self, folder, when):
        return build_pin(CHAT, 2, "CF", folder, "claude", "claude", "s1", when)

    def test_store_roundtrip_and_toggle(self):
        p = self.pin("/p", NOW)
        self.store.save(p)
        self.assertEqual(self.store.load(p.id), p)
        self.assertEqual(self.store.toggle(p.id, 1).checked, {1})
        self.assertEqual(self.store.load(p.id).checked, {1})
        self.assertEqual(self.store.toggle(p.id, 1).checked, set())

    def test_load_missing_none(self):
        self.assertIsNone(self.store.load("nope"))

    def test_list_for_folder_filters_and_sorts(self):
        a = self.pin("/p", datetime(2026, 1, 1, 0, 0, 0))
        b = self.pin("/p", datetime(2026, 1, 2, 0, 0, 0))
        c = self.pin("/other", datetime(2026, 1, 3, 0, 0, 0))
        for p in (a, b, c):
            self.store.save(p)
        self.assertEqual([p.id for p in self.store.list_for_folder("/p")], [b.id, a.id])

    def test_corrupt_pin_file_ignored(self):
        (self.dir / "pins").mkdir(parents=True, exist_ok=True)
        (self.dir / "pins" / "bad.json").write_text("{nope")
        self.assertEqual(self.store.list_for_folder("/p"), [])
        self.assertIsNone(self.store.load("bad"))
