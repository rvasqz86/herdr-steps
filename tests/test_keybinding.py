import shutil
import tempfile
import tomllib
import unittest
from datetime import datetime
from pathlib import Path

from steps.keybinding import BLOCK, apply_binding, ensure_binding

EXISTING = """[theme]
name = "x"

[keys]
split_horizontal = ["prefix+minus", "ctrl+alt+shift+d"]

[[keys.command]]
key = "ctrl+alt+n"
type = "popup"
command = "hq new"

[ui]
mouse = true
"""
NOW = datetime(2026, 11, 13, 10, 0, 0)


class EnsureBindingTest(unittest.TestCase):
    def test_adds_to_existing_config(self):
        text, status = ensure_binding(EXISTING)
        self.assertEqual(status, "added")
        self.assertEqual(text, EXISTING + BLOCK)
        parsed = tomllib.loads(text)
        self.assertEqual(parsed["ui"], {"mouse": True})
        self.assertEqual(parsed["keys"]["command"][-1]["command"], "local.steps.mark")

    def test_adds_newline_when_missing(self):
        text, _ = ensure_binding('[ui]\nmouse = true')
        self.assertTrue(text.startswith('[ui]\nmouse = true\n'))
        tomllib.loads(text)

    def test_idempotent(self):
        once, _ = ensure_binding(EXISTING)
        twice, status = ensure_binding(once)
        self.assertEqual((twice, status), (once, "already"))

    def test_conflict_in_keys_table(self):
        src = '[keys]\nfoo = ["prefix+m"]\n'
        self.assertEqual(ensure_binding(src), (src, "conflict:foo"))

    def test_conflict_string_value(self):
        src = '[keys]\nbar = "prefix+m"\n'
        self.assertEqual(ensure_binding(src), (src, "conflict:bar"))

    def test_conflict_in_command_entry(self):
        src = '[[keys.command]]\nkey = "prefix+m"\ntype = "shell"\ncommand = "ls"\n'
        self.assertEqual(ensure_binding(src), (src, "conflict:command ls"))

    def test_invalid_toml_raises(self):
        with self.assertRaises(ValueError):
            ensure_binding("[keys\n")


class ApplyBindingTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.cfg = self.dir / "config.toml"

    def test_apply_creates_backup(self):
        self.cfg.write_text(EXISTING)
        self.assertEqual(apply_binding(self.cfg, NOW), "added")
        backup = self.dir / "config.toml.bak-herdr-steps-20261113-100000"
        self.assertEqual(backup.read_text(), EXISTING)
        self.assertEqual(self.cfg.read_text(), EXISTING + BLOCK)

    def test_apply_already_no_backup(self):
        self.cfg.write_text(EXISTING + BLOCK)
        self.assertEqual(apply_binding(self.cfg, NOW), "already")
        self.assertEqual(len(list(self.dir.iterdir())), 1)

    def test_apply_conflict_leaves_file(self):
        self.cfg.write_text('[keys]\nfoo = "prefix+m"\n')
        self.assertEqual(apply_binding(self.cfg, NOW), "conflict:foo")
        self.assertEqual(self.cfg.read_text(), '[keys]\nfoo = "prefix+m"\n')

    def test_apply_missing_file_creates(self):
        cfg = self.dir / "sub" / "config.toml"
        self.assertEqual(apply_binding(cfg, NOW), "added")
        self.assertEqual(cfg.read_text(), BLOCK.lstrip())
        tomllib.loads(cfg.read_text())


class InlineCommandTest(unittest.TestCase):
    def test_inline_command_array_refused(self):
        src = '[keys]\ncommand = [{ key = "ctrl+x", type = "shell", command = "ls" }]\n'
        text, status = ensure_binding(src)
        self.assertEqual(text, src)
        self.assertTrue(status.startswith("conflict:"), status)

    def test_inline_keys_table_refused(self):
        src = 'keys = { prefix = "ctrl+a" }\n'
        text, status = ensure_binding(src)
        self.assertEqual(text, src)
        self.assertTrue(status.startswith("conflict:"), status)

    def test_apply_inline_leaves_file_untouched(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        cfg = d / "config.toml"
        src = "keys.command = []\n"
        cfg.write_text(src)
        status = apply_binding(cfg, NOW)
        self.assertTrue(status.startswith("conflict:"), status)
        self.assertEqual(cfg.read_text(), src)
        self.assertEqual(len(list(d.iterdir())), 1)
