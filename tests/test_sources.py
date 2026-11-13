import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from steps.herdr import HerdrCli, HerdrError
from steps.sources import load_turns
from steps.sources.scrollback import scrollback_turns

FIXTURE = Path(__file__).parent / "fixtures" / "claude_basic.jsonl"


class FakeRun:
    def __init__(self, outputs=None, returncode=0, stderr=""):
        self.calls = []
        self.outputs = outputs or {}
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        out = ""
        for key, value in self.outputs.items():
            if key in argv:
                out = value
        return subprocess.CompletedProcess(argv, self.returncode, out, self.stderr)


def pane_json(**pane):
    return json.dumps({"id": "cli:pane:get", "result": {"pane": pane}})


class HerdrCliTest(unittest.TestCase):
    def test_pane_get_parses_result(self):
        run = FakeRun({"get": pane_json(pane_id="w1:p1", cwd="/p")})
        pane = HerdrCli("hb", run=run).pane_get("w1:p1")
        self.assertEqual(pane["cwd"], "/p")
        self.assertEqual(run.calls[0], ["hb", "pane", "get", "w1:p1"])

    def test_pane_read_argv(self):
        run = FakeRun({"read": "a\nb\n"})
        self.assertEqual(HerdrCli("hb", run=run).pane_read("w1:p1", lines=50), "a\nb\n")
        self.assertEqual(
            run.calls[0],
            ["hb", "pane", "read", "w1:p1", "--source", "recent-unwrapped", "--lines", "50"],
        )

    def test_open_pane_argv(self):
        run = FakeRun()
        HerdrCli("hb", run=run).open_pane(
            "pin", "split", target_pane="w1:p1", direction="right",
            env={"HERDR_STEPS_PIN": "abc"}, focus=False,
        )
        self.assertEqual(
            run.calls[0],
            ["hb", "plugin", "pane", "open", "--plugin", "local.steps",
             "--entrypoint", "pin", "--placement", "split",
             "--target-pane", "w1:p1", "--direction", "right",
             "--env", "HERDR_STEPS_PIN=abc", "--no-focus"],
        )

    def test_open_popup_argv(self):
        run = FakeRun()
        HerdrCli("hb", run=run).open_pane("picker", "popup", width="80%", height="70%")
        self.assertEqual(
            run.calls[0][-6:],
            ["popup", "--width", "80%", "--height", "70%", "--focus"],
        )

    def test_error_on_nonzero(self):
        run = FakeRun(returncode=1, stderr="ui_busy")
        with self.assertRaises(HerdrError) as ctx:
            HerdrCli("hb", run=run).pane_get("w1:p1")
        self.assertIn("ui_busy", str(ctx.exception))

    def test_bin_from_env(self):
        import os
        old = os.environ.get("HERDR_BIN_PATH")
        os.environ["HERDR_BIN_PATH"] = "/x/herdr"
        try:
            self.assertEqual(HerdrCli().bin, "/x/herdr")
        finally:
            if old is None:
                del os.environ["HERDR_BIN_PATH"]
            else:
                os.environ["HERDR_BIN_PATH"] = old


class FakeHerdr:
    def __init__(self, scrollback=""):
        self.scrollback = scrollback
        self.reads = 0

    def pane_read(self, pane_id, lines=2000):
        self.reads += 1
        return self.scrollback


class LoadTurnsTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)

    def claude_pane(self, session="sess-1"):
        return {"pane_id": "w1:p1", "cwd": "/p", "agent": "claude",
                "agent_session": {"value": session}}

    def test_scrollback_turns(self):
        self.assertEqual(
            [t.text for t in scrollback_turns("a  \n\n  \nb\n")], ["a", "b"]
        )

    def test_load_turns_claude(self):
        proj = self.home / ".claude" / "projects" / "-p"
        proj.mkdir(parents=True)
        shutil.copy(FIXTURE, proj / "sess-1.jsonl")
        herdr = FakeHerdr("x")
        turns, source = load_turns(self.claude_pane(), herdr, self.home)
        self.assertEqual(source, "claude")
        self.assertEqual(turns[0].role, "user")
        self.assertEqual(herdr.reads, 0)

    def test_load_turns_falls_back_when_claude_file_missing(self):
        turns, source = load_turns(self.claude_pane(), FakeHerdr("line one\n"), self.home)
        self.assertEqual((source, [t.text for t in turns]), ("scrollback", ["line one"]))

    def test_load_turns_falls_back_for_other_agents(self):
        pane = {"pane_id": "w1:p2", "cwd": "/p", "agent": "cursor"}
        turns, source = load_turns(pane, FakeHerdr("hi\n"), self.home)
        self.assertEqual(source, "scrollback")

    def test_load_turns_falls_back_when_scrollback_errors_too(self):
        class Broken:
            def pane_read(self, *a, **k):
                raise HerdrError("gone")
        self.assertEqual(load_turns({"pane_id": "x", "cwd": "/p"}, Broken(), self.home), ([], "none"))

    def test_load_turns_none(self):
        pane = {"pane_id": "w1:p2", "cwd": "/p"}
        self.assertEqual(load_turns(pane, FakeHerdr(""), self.home), ([], "none"))
