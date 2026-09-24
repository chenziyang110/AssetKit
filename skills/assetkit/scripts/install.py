#!/usr/bin/env python3
"""Install AssetKit into one project; optionally initialize and wire its entry rules.

No network calls, no automatic upgrades, no asset moves. Existing differing skill
files are rejected before writes. Use --dry-run to inspect the plan.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

SOURCE = Path(__file__).resolve().parents[1]
CLIENTS = {
    "codex": (".agents/skills/assetkit", "AGENTS.md"),
    "claude": (".claude/skills/assetkit", "CLAUDE.md"),
}


def safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    path.relative_to(root)
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Refusing a symlink target: {current}")
    path.resolve().relative_to(root)
    return path


def merge_block(original: str, body: str, start: str, end: str) -> str:
    if original.count(start) != original.count(end) or original.count(start) > 1:
        raise ValueError("Malformed or duplicated AssetKit markers; repair them before installing")
    block = start + "\n" + body.rstrip() + "\n" + end
    if start in original:
        first, last = original.index(start), original.index(end)
        if last < first:
            raise ValueError("AssetKit markers are out of order")
        return original[:first] + block + original[last + len(end):]
    separator = "" if not original else ("\n" if original.endswith("\n") else "\n\n")
    return original + separator + block + "\n"


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".assetkit-install-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Project root must be an existing directory")
    relative, entry_name = CLIENTS[args.client]
    target = safe_path(root, relative)
    copies: dict[Path, bytes] = {}
    entries: dict[Path, bytes] = {}
    for source in sorted(SOURCE.rglob("*")):
        if "__pycache__" in source.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        if source.is_symlink():
            raise ValueError(f"Skill package contains a symlink: {source}")
        if not source.is_file():
            continue
        destination = safe_path(root, relative + "/" + source.relative_to(SOURCE).as_posix())
        payload = source.read_bytes()
        if destination.exists():
            if not destination.is_file() or destination.read_bytes() != payload:
                raise ValueError(f"Existing skill file differs; back up and review it before replacement: {destination}")
        else:
            copies[destination] = payload
    if args.bootstrap:
        for name in (".assets", ".assets/records", ".assets/cache", ".assets/.lock", ".assets/config.json"):
            safe_path(root, name)
        template = (SOURCE / "assets/project-entry.md").read_text(encoding="utf-8")
        rules = template.replace("{{SKILL_PATH}}", relative)
        ignore = (SOURCE / "assets/gitignore-snippet.txt").read_text(encoding="utf-8")
        for name, body, start, end in (
            (entry_name, rules, "<!-- assetkit:start -->", "<!-- assetkit:end -->"),
            (".gitignore", ignore, "# assetkit:start", "# assetkit:end"),
        ):
            path = safe_path(root, name)
            previous = path.read_bytes() if path.exists() else b""
            updated = merge_block(previous.decode("utf-8"), body, start, end).encode("utf-8")
            if previous != updated:
                entries[path] = updated
        import launcher
        command = launcher.plan(root, relative)
        if command:
            entries[command[0]] = command[1]
    plan: dict[str, Any] = {
        "ok": True, "dry_run": args.dry_run, "client": args.client,
        "project": str(root), "skill_path": relative,
        "copy_count": len(copies),
        "entry_files": [p.relative_to(root).as_posix() for p in entries],
        "bootstrap": args.bootstrap,
    }
    if args.dry_run:
        return plan
    for path, payload in copies.items():
        atomic_write(path, payload)
    if args.bootstrap:
        proc = subprocess.run(
            [sys.executable, "-S", str(target / "scripts/assetctl.py"), "--root", str(root), "init"],
            capture_output=True, text=True, encoding="utf-8", check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        if proc.returncode != 0:
            raise ValueError("Skill files copied, but ledger initialization failed: " + (proc.stderr or proc.stdout).strip())
        plan["ledger"] = json.loads(proc.stdout)
        for path, payload in entries.items():
            atomic_write(path, payload)
    plan["notice"] = "Skill files installed. Confirm discovery in your agent; implicit activation is not guaranteed."
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Existing target project root")
    parser.add_argument("--client", choices=sorted(CLIENTS), required=True)
    parser.add_argument("--bootstrap", action="store_true", help="Initialize ledger and merge marked project entry/gitignore rules")
    parser.add_argument("--dry-run", action="store_true", help="Validate and describe changes without writing")
    try:
        print(json.dumps(install(parser.parse_args()), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
