"""Bootstrap must work independently of the installer's copy mode."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1] / "skills/assetkit"


def snapshot(path):
    return {p.relative_to(path).as_posix(): p.read_bytes()
            for p in path.rglob("*") if p.is_file()}


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="assetkit bootstrap ")
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.package = self.base / "global-skill"
        shutil.copytree(SKILL, self.package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *extra, script=None, project=None, ok=True):
        script = script or self.package / "scripts/bootstrap.py"
        proc = subprocess.run([sys.executable, "-S", str(script), "--project", str(project or self.root), *extra],
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PYTHONUTF8": "1"})
        result = json.loads(proc.stdout or proc.stderr)
        self.assertEqual(proc.returncode == 0, ok, result)
        return result

    def test_global_source_remains_unchanged_and_project_rules_preserved(self):
        before = snapshot(self.package)
        (self.root / "AGENTS.md").write_bytes(b"# Existing\r\nKeep this.\r\n")
        self.call("--entry", "both")
        self.assertEqual(snapshot(self.package), before)
        self.assertFalse((self.package / ".assets").exists())
        self.assertTrue((self.root / "AGENTS.md").read_bytes().startswith(b"# Existing\r\nKeep this.\r\n"))
        self.assertIn(self.package.as_posix(), (self.root / "CLAUDE.md").read_text(encoding="utf-8"))
        config = (self.root / ".assets/config.json").read_bytes()
        (self.root / ".assets/records/keep.txt").write_text("preserve this record", encoding="utf-8")
        again = self.call("--entry", "both")
        self.assertEqual(again["entry_files"], [])
        self.assertEqual(config, (self.root / ".assets/config.json").read_bytes())
        self.assertEqual((self.root / ".assets/records/keep.txt").read_text(), "preserve this record")

    def test_default_cli_symlink_layout(self):
        canonical = self.root / ".agents/skills/assetkit"
        canonical.parent.mkdir(parents=True)
        shutil.copytree(self.package, canonical)
        linked = self.root / ".claude/skills/assetkit"
        linked.parent.mkdir(parents=True)
        try:
            linked.symlink_to(canonical, target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        before = snapshot(canonical)
        self.call("--entry", "CLAUDE.md", script=linked / "scripts/bootstrap.py")
        self.assertTrue(linked.is_symlink())
        self.assertEqual(snapshot(canonical), before)
        rules = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(".agents/skills/assetkit/SKILL.md", rules)

    def test_copy_install_and_relative_entry(self):
        copied = self.root / ".claude/skills/assetkit"
        copied.parent.mkdir(parents=True)
        shutil.copytree(self.package, copied)
        before = snapshot(copied)
        self.call("--entry", "CLAUDE.md", script=copied / "scripts/bootstrap.py")
        self.assertEqual(snapshot(copied), before)
        self.assertIn(".claude/skills/assetkit/SKILL.md", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_dry_run_and_no_rule_entry(self):
        self.call("--dry-run", "--entry", "both")
        self.assertEqual(list(self.root.iterdir()), [])
        self.call("--entry", "none")
        self.assertTrue((self.root / ".assets/config.json").exists())
        self.assertTrue((self.root / ".gitignore").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse((self.root / "CLAUDE.md").exists())

    def test_malformed_markers_fail_before_writes(self):
        entry = self.root / "AGENTS.md"
        entry.write_text("<!-- assetkit:start -->\nbroken", encoding="utf-8")
        self.call(ok=False)
        self.assertFalse((self.root / ".assets").exists())
        self.assertFalse((self.root / ".gitignore").exists())

    def test_metadata_symlinks_still_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        try:
            (self.root / ".assets").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        self.call(ok=False)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_state_cannot_be_written_inside_skill(self):
        self.call(project=self.package, ok=False)
        self.assertFalse((self.package / ".assets").exists())

    def test_marketplace_matches_single_canonical_skill(self):
        repo = SKILL.parents[1]
        manifest = json.loads((repo / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(manifest["plugins"][0]["skills"], ["./skills/assetkit"])
        self.assertFalse((repo / "SKILL.md").exists())
        found = sorted(p.relative_to(repo).as_posix() for p in (repo / "skills").rglob("SKILL.md"))
        self.assertEqual(found, ["skills/assetkit/SKILL.md"])


if __name__ == "__main__":
    unittest.main()
