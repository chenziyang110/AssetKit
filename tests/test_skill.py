"""Packaging and non-destructive installation tests; no network or model required."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1] / "skills/assetkit"
INSTALL = SKILL / "scripts/install.py"


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="assetkit test ")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_install(self, *extra, client="codex", ok=True, script=INSTALL):
        proc = subprocess.run(
            [sys.executable, "-S", str(script), "--project", str(self.root), "--client", client, *extra],
            capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"},
        )
        data = json.loads(proc.stdout or proc.stderr)
        self.assertEqual(proc.returncode == 0, ok, data)
        return data

    def test_skill_metadata_and_links(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        front = text.split("---", 2)[1]
        self.assertIn("\nname: assetkit\n", front)
        description = re.search(r"^description: (.+)$", front, re.MULTILINE).group(1)
        self.assertTrue(1 <= len(description) <= 1024)
        self.assertLess(len(text.splitlines()), 500)
        links = re.findall(r"\]\(((?:references|assets)/[^)]+)\)", text)
        self.assertGreaterEqual(len(links), 6)
        for relative in links:
            self.assertTrue((SKILL / relative).is_file(), relative)

    def test_dry_run_changes_nothing(self):
        result = self.run_install("--bootstrap", "--dry-run")
        self.assertGreater(result["copy_count"], 0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_copy_only_does_not_create_ledger(self):
        self.run_install()
        self.assertTrue((self.root / ".agents/skills/assetkit/SKILL.md").is_file())
        self.assertFalse((self.root / ".assets").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_bootstrap_preserves_rules_and_is_idempotent(self):
        (self.root / "AGENTS.md").write_bytes(b"# Existing rules\r\nKeep this rule.\r\n")
        (self.root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        self.run_install("--bootstrap")
        config = (self.root / ".assets/config.json").read_bytes()
        first = (self.root / "AGENTS.md").read_bytes()
        self.assertTrue(first.startswith(b"# Existing rules\r\nKeep this rule.\r\n"))
        second = self.run_install("--bootstrap")
        self.assertEqual(second["copy_count"], 0)
        self.assertEqual(second["entry_files"], [])
        self.assertEqual((self.root / ".assets/config.json").read_bytes(), config)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), first)
        self.assertEqual(first.count(b"<!-- assetkit:start -->"), 1)
        self.assertTrue((self.root / ".gitignore").read_text().startswith("node_modules/\n"))

    def test_claude_entry_and_running_installed_installer(self):
        self.run_install("--bootstrap", client="claude")
        installed = self.root / ".claude/skills/assetkit/scripts/install.py"
        self.run_install("--bootstrap", client="claude", script=installed)
        rules = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(".claude/skills/assetkit/SKILL.md", rules)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_modified_skill_is_not_overwritten(self):
        self.run_install()
        path = self.root / ".agents/skills/assetkit/SKILL.md"
        path.write_text("local customization", encoding="utf-8")
        self.run_install("--bootstrap", ok=False)
        self.assertEqual(path.read_text(), "local customization")
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse((self.root / ".assets").exists())

    def test_malformed_entry_rejected_before_install(self):
        path = self.root / "AGENTS.md"
        path.write_text("Keep\n<!-- assetkit:start -->\nbroken", encoding="utf-8")
        self.run_install("--bootstrap", ok=False)
        self.assertFalse((self.root / ".agents").exists())
        self.assertFalse((self.root / ".assets").exists())

    def test_symlink_install_target_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            try:
                (self.root / ".agents").symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(str(exc))
            self.run_install(ok=False)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_patch_file_and_metadata_symlink(self):
        self.run_install("--bootstrap")
        tool = self.root / ".agents/skills/assetkit/scripts/assetctl.py"
        asset = self.root / "notes.md"
        asset.write_text("a reusable note", encoding="utf-8")
        request = {
            "type": "document", "domain": "engineering", "logical_key": "engineering/notes",
            "title": "Notes", "summary": "Reference note", "use_when": ["Planning work"],
            "storage_policy": "in-place", "files": [{"path": "notes.md", "role": "primary"}],
        }
        manifest = self.root / "request.json"
        manifest.write_text(json.dumps(request), encoding="utf-8")
        def call(*args):
            return subprocess.run([sys.executable, "-S", str(tool), "--root", str(self.root), *args],
                                  capture_output=True, text=True, encoding="utf-8",
                                  env={**os.environ, "PYTHONUTF8": "1"})
        added = call("add", "--manifest", str(manifest), "--request-key", "note.v1")
        self.assertEqual(added.returncode, 0, added.stderr)
        patch = self.root / "patch.json"
        patch.write_text('{"tags":["planning"]}', encoding="utf-8")
        result = call("patch", json.loads(added.stdout)["id"], "--expect-revision", "1", "--patch-file", str(patch))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["revision"], 2)
        config = self.root / ".assets/config.json"
        original = config.read_bytes()
        other = self.root / "other-config.json"
        other.write_bytes(original)
        config.unlink()
        try:
            config.symlink_to(other)
        except OSError as exc:
            config.write_bytes(original)
            self.skipTest(str(exc))
        self.assertNotEqual(call("search", "notes").returncode, 0)


if __name__ == "__main__":
    unittest.main()
