#!/usr/bin/env python3
"""Exercise the real npm skills CLI in disposable projects (requires network)."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
EXPECTED = REPO / "skills/assetkit"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def files(path: Path) -> dict[str, str]:
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Local repo path or owner/repo")
    parser.add_argument("--cli-version", default="latest")
    args = parser.parse_args()
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("Node.js and npx must be installed")
    with tempfile.TemporaryDirectory(prefix="assetkit-cli-") as temp:
        base = Path(temp)
        home = base / "home"
        home.mkdir()
        env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
               "XDG_CONFIG_HOME": str(home / ".config"), "CODEX_HOME": str(home / ".codex"),
               "DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1", "CI": "1",
               "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        cli = [npx, "--yes", f"skills@{args.cli_version}"]

        def run(command: list[str], cwd: Path) -> str:
            print("$ " + " ".join(command), flush=True)
            proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=180)
            print(proc.stdout, flush=True)
            if proc.stderr:
                print(proc.stderr, file=sys.stderr, flush=True)
            if proc.returncode:
                raise RuntimeError(f"Command failed ({proc.returncode}): {command}")
            return ANSI.sub("", proc.stdout)

        version = run([*cli, "--version"], base).strip()
        listing = run([*cli, "add", args.source, "--list"], base)
        if "assetkit" not in listing or not re.search(r"Found\s+1\s+skill", listing, re.I):
            raise RuntimeError("Expected discovery of exactly one skill named assetkit")
        results = []
        for mode in ("project-default", "project-copy", "global-default"):
            project = base / mode
            project.mkdir()
            (project / "AGENTS.md").write_text("# Existing rules\nKeep this instruction.\n", encoding="utf-8")
            options = ["--copy"] if mode == "project-copy" else (["--global"] if mode == "global-default" else [])
            run([*cli, "add", args.source, "--skill", "assetkit", "--agent", "codex", "claude-code", "--yes", *options], project)
            if mode == "global-default":
                codex = home / ".codex/skills/assetkit"
                claude = home / ".claude/skills/assetkit"
            else:
                codex = project / ".agents/skills/assetkit"
                claude = project / ".claude/skills/assetkit"
            for installed in (codex, claude):
                if not (installed / "SKILL.md").is_file():
                    raise RuntimeError(f"Missing installed skill: {installed}")
                if files(installed) != files(EXPECTED):
                    raise RuntimeError(f"Installed package differs from the checked-out skill: {installed}")
            if (project / ".assets").exists():
                raise RuntimeError("Skill installation must not initialize a business ledger")
            before = files(codex)
            bootstrap = [sys.executable, "-B", "-S", str(claude / "scripts/bootstrap.py"),
                         "--project", str(project), "--entry", "both"]
            run(bootstrap, project)
            config = (project / ".assets/config.json").read_bytes()
            run(bootstrap, project)
            if config != (project / ".assets/config.json").read_bytes() or files(codex) != before:
                raise RuntimeError("Bootstrap changed project identity or installed skill content")
            if not (project / "AGENTS.md").read_text().startswith("# Existing rules\nKeep this instruction.\n"):
                raise RuntimeError("Bootstrap replaced pre-existing project rules")
            note = project / "notes.md"
            note.write_text("# 首页资产\n用于中文检索的测试文档。", encoding="utf-8")
            request = {"type": "document", "domain": "engineering", "logical_key": "engineering/notes",
                       "title": "首页说明", "summary": "首页产品说明", "use_when": ["制作首页"],
                       "storage_policy": "in-place", "files": [{"path": "notes.md", "role": "primary"}]}
            manifest = project / "request.json"
            manifest.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            tool = [sys.executable, "-B", "-S", str(codex / "scripts/assetctl.py"), "--root", str(project)]
            added = json.loads(run([*tool, "add", "--manifest", str(manifest), "--request-key", "smoke.note.v1"], project))
            search = json.loads(run([*tool, "search", "首页", "--status", "all", "--limit", "5"], project))
            if search["total"] != 1 or search["items"][0]["id"] != added["id"]:
                raise RuntimeError("Installed CLI failed Chinese discovery")
            run([*tool, "validate", "--hashes"], project)
            if files(codex) != before or (codex / ".assets").exists():
                raise RuntimeError("Project operations wrote into the installed skill")
            results.append({"mode": mode, "ok": True, "claude_symlink": claude.is_symlink()})
        print(json.dumps({"ok": True, "source": args.source, "cli_version": version,
                          "telemetry": "disabled", "scenarios": results}, indent=2))


if __name__ == "__main__":
    main()
