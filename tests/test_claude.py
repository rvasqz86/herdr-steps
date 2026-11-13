import os
import shutil
import tempfile
import unittest
from pathlib import Path

from steps.sources.claude import find_claude_session, read_claude_turns

FIXTURE = Path(__file__).parent / "fixtures" / "claude_basic.jsonl"


class ReadClaudeTurnsTest(unittest.TestCase):
    def test_reads_turns_in_order(self):
        turns = read_claude_turns(FIXTURE)
        self.assertEqual(
            [(t.role, t.text.split("\n")[0]) for t in turns],
            [
                ("user", "how do I get myapp on cloudflare?"),
                ("agent", "You'll need an account. Then:"),
                ("tool", "Bash: npm run build"),
                ("agent", "Build passed."),
                ("user", "ok, now the DNS part?"),
            ],
        )

    def test_consecutive_agent_text_merges(self):
        agent = read_claude_turns(FIXTURE)[1]
        self.assertTrue(agent.text.endswith("2. Connect the repo\n3. Add env vars"))

    def test_skips_partial_last_line(self):
        self.assertEqual(read_claude_turns(FIXTURE)[-1].text, "ok, now the DNS part?")

    def test_tool_summary(self):
        self.assertEqual(read_claude_turns(FIXTURE)[2].text, "Bash: npm run build")

    def test_timestamp_copied(self):
        self.assertEqual(read_claude_turns(FIXTURE)[0].timestamp, "2026-11-13T10:00:02Z")


class FindClaudeSessionTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        self.proj = self.home / ".claude" / "projects" / "-home-u-my-app"
        self.proj.mkdir(parents=True)

    def test_find_by_session_id(self):
        f = self.proj / "abc-123.jsonl"
        f.write_text("")
        self.assertEqual(find_claude_session("abc-123", "/elsewhere", self.home), f)

    def test_find_newest_by_cwd(self):
        old = self.proj / "old.jsonl"
        new = self.proj / "new.jsonl"
        old.write_text("")
        new.write_text("")
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))
        self.assertEqual(find_claude_session(None, "/home/u/my.app", self.home), new)

    def test_find_missing_returns_none(self):
        self.assertIsNone(find_claude_session("nope", "/nowhere", self.home))
        self.assertIsNone(find_claude_session(None, "/nowhere", self.home))
