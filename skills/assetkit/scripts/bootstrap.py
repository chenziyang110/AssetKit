#!/usr/bin/env python3
"""Initialize a project after skills CLI installation, without copying the skill.

The installed skill may be a symlink, a copy, or a global installation. Only
project metadata and explicitly selected entry files are written. No network.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

# Import shared helpers without creating __pycache__ in the installed package.
sys.dont_write_bytecode = True
from install import SOURCE, atomic_write, merge_block, safe_path

ENTRIES = {
    "AGENTS.md": ("AGENTS.md",),
    "CLAUDE.md": ("CLAUDE.md",),
    "both": ("AGENTS.md", "CLAUDE.md"),
    "none": (),
}


def bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Project root must be an existing directory")
    if root == SOURCE or SOURCE in root.parents:
        raise ValueError("Project state must not be initialized inside the installed skill")
    for relative in (".assets", ".assets/records", ".assets/cache", ".assets/.lock", ".assets/config.json"):
        safe_path(root, relative)
    try:
        skill_path = SOURCE.relative_to(root).as_posix()
    except ValueError:
        # Global installations need a real absolute path, not an assumed client variable.
        skill_path = SOURCE.as_posix()
    template = (SOURCE / "assets/project-entry.md").read_text(encoding="utf-8")
    rules = template.replace("{{SKILL_PATH}}", skill_path)
    ignore = (SOURCE / "assets/gitignore-snippet.txt").read_text(encoding="utf-8")
    blocks = [(name, rules, "<!-- assetkit:start -->", "<!-- assetkit:end -->")
              for name in ENTRIES[args.entry]]
    blocks.append((".gitignore", ignore, "# assetkit:start", "# assetkit:end"))
    updates: dict[Path, bytes] = {}
    for name, body, start, end in blocks:
        path = safe_path(root, name)
        previous = path.read_bytes() if path.exists() else b""
        updated = merge_block(previous.decode("utf-8"), body, start, end).encode("utf-8")
        if previous != updated:
            updates[path] = updated
    result: dict[str, Any] = {
        "ok": True, "dry_run": args.dry_run, "project": str(root),
        "skill_path": skill_path, "copy_count": 0,
        "entry_files": [p.relative_to(root).as_posix() for p in updates],
        "ledger_exists": (root / ".assets/config.json").is_file(),
    }
    if args.dry_run:
        return result
    proc = subprocess.run(
        [sys.executable, "-B", "-S", str(SOURCE / "scripts/assetctl.py"), "--root", str(root), "init"],
        capture_output=True, text=True, encoding="utf-8", check=False,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if proc.returncode:
        raise ValueError("Ledger initialization failed; entry files unchanged: " + (proc.stderr or proc.stdout).strip())
    result["ledger"] = json.loads(proc.stdout)
    result["ledger"].pop("next", None)  # The legacy init hint is unnecessary after bootstrap.
    for path, payload in updates.items():
        atomic_write(path, payload)
    result["notice"] = "Project initialized; installed skill unchanged. Confirm discovery in your agent."
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Existing target project root")
    parser.add_argument("--entry", choices=sorted(ENTRIES), default="AGENTS.md",
                        help="Project rules to merge; none still initializes the ledger and .gitignore")
    parser.add_argument("--dry-run", action="store_true", help="Inspect planned changes without writing")
    try:
        print(json.dumps(bootstrap(parser.parse_args()), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
