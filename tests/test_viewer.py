import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from steps import __main__ as main
from steps.model import Pin, PinLine
from steps.viewer import ViewerState


def pin():
    return Pin(
        id="p1", name="CF setup", folder="/p", source="claude", agent="claude",
        session_id="s", created_at="2026-11-13T10:00:00",
        lines=[
            PinLine("user", "> how?"),
            PinLine("blank", ""),
            PinLine("text", "Then:"),
            PinLine("step", "1. Create", 0),
            PinLine("step", "2. Add vars:", 1),
            PinLine("text", "   DATABASE_URL", 1),
            PinLine("tool", "⏺ Bash: x"),
            PinLine("step", "3. Domain", 2),
        ],
        checked={0},
    )


class ViewerStateTest(unittest.TestCase):
    def test_header_progress(self):
        self.assertEqual(ViewerState(pin()).header(), "★ CF setup · 1/3")

    def test_cursor_starts_on_first_step(self):
        self.assertEqual(ViewerState(pin()).cursor_row, 3)

    def test_cursor_skips_non_steps(self):
        s = ViewerState(pin())
        s.move(1)
        s.move(1)
        self.assertEqual(s.cursor_row, 7)
        s.move(1)
        self.assertEqual(s.cursor_row, 7)
        s.move(-5)
        self.assertEqual(s.cursor_row, 3)

    def test_toggle_at_cursor(self):
        s = ViewerState(pin())
        self.assertEqual(s.toggle_at_cursor(), 0)
        self.assertEqual(s.pin.checked, set())

    def test_toggle_row(self):
        s = ViewerState(pin())
        self.assertEqual(s.toggle_row(7), 2)
        self.assertEqual(s.pin.checked, {0, 2})
        self.assertEqual(s.cursor_row, 7)

    def test_toggle_row_non_step_none(self):
        s = ViewerState(pin())
        self.assertIsNone(s.toggle_row(5))
        self.assertIsNone(s.toggle_row(0))
        self.assertIsNone(s.toggle_row(99))
        self.assertEqual(s.pin.checked, {0})

    def test_no_steps(self):
        p = pin()
        p.lines = [PinLine("text", "hello")]
        s = ViewerState(p)
        self.assertIsNone(s.cursor_row)
        self.assertIsNone(s.toggle_at_cursor())
        s.move(1)


class SetupAndPinCommandTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def test_setup_added_reloads(self):
        calls = []
        cfg = self.dir / "config.toml"
        cfg.write_text("[ui]\nmouse = true\n")
        rc = main.cmd_setup({"HERDR_CONFIG_PATH": str(cfg)}, lambda: calls.append("reload"),
                            datetime(2026, 11, 13))
        self.assertEqual((rc, calls), (0, ["reload"]))

    def test_setup_conflict_exits_1(self):
        cfg = self.dir / "config.toml"
        cfg.write_text('[keys]\nfoo = "prefix+m"\n')
        calls = []
        rc = main.cmd_setup({"HERDR_CONFIG_PATH": str(cfg)}, lambda: calls.append(1),
                            datetime(2026, 11, 13))
        self.assertEqual((rc, calls), (1, []))

    def test_config_path_default(self):
        self.assertEqual(main.config_path({}, Path("/h")), Path("/h/.config/herdr/config.toml"))

    def test_pin_missing_shows_message(self):
        shown = []
        rc = main.cmd_pin({"HERDR_STEPS_PIN": "nope", "HERDR_PLUGIN_STATE_DIR": str(self.dir)},
                          shown.append, lambda *a: None)
        self.assertEqual(rc, 0)
        self.assertEqual(shown, ["That pin no longer exists"])


class ViewerScrollTest(unittest.TestCase):
    def test_scroll_by_reaches_end_without_following_cursor(self):
        s = ViewerState(pin())
        for _ in range(5):
            s.scroll_by(21, total_rows=84, body_h=21)
        self.assertEqual(s.scroll, 63)
        self.assertFalse(s.follow_cursor)

    def test_scroll_by_clamps_at_top(self):
        s = ViewerState(pin())
        s.scroll_by(-10, total_rows=84, body_h=21)
        self.assertEqual(s.scroll, 0)

    def test_move_resumes_following(self):
        s = ViewerState(pin())
        s.scroll_by(5, total_rows=84, body_h=21)
        self.assertTrue(s.move(1))
        self.assertTrue(s.follow_cursor)

    def test_move_without_steps_returns_false(self):
        p = pin()
        p.lines = [PinLine("text", "hello")]
        self.assertFalse(ViewerState(p).move(1))

    def test_focus_first_visible(self):
        s = ViewerState(pin())
        # display rows: (pin line index, text); steps are pin lines 3, 4, 7
        rows = [(i, "") for i in range(8)]
        s.scroll = 5
        s.focus_first_visible(rows, body_h=3)
        self.assertEqual(s.cursor_row, 7)
        s.scroll = 0
        s.focus_first_visible(rows, body_h=2)  # no step in view → cursor unchanged
        self.assertEqual(s.cursor_row, 7)
