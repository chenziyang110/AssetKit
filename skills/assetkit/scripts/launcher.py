"""Non-destructive project-local short command. Never embed business state."""
from __future__ import annotations
import json
from pathlib import Path


def content(skill_path: str) -> bytes:
    return ('''#!/usr/bin/env python3
# AssetKit managed launcher v1. Re-run bootstrap after changing installations.
import json
from pathlib import Path
import runpy
import sys
sys.dont_write_bytecode = True
SKILL_PATH = ''' + json.dumps(skill_path, ensure_ascii=True) + '''
root = Path(__file__).resolve().parent.parent
target = (root / SKILL_PATH / "scripts/agent.py").resolve()
if not target.is_file():
    print(json.dumps({"ok": False, "code": "SKILL_MISSING", "next": "install assetkit and re-run bootstrap"}))
    raise SystemExit(2)
sys.path.insert(0, str(target.parent))
sys.argv = [str(target), "--root", str(root), *sys.argv[1:]]
runpy.run_path(str(target), run_name="__main__")
''').encode('utf-8')


def plan(root: Path, skill_path: str) -> tuple[Path, bytes] | None:
    from install import safe_path
    path = safe_path(root, '.assets/ak.py')
    data = content(skill_path)
    if path.exists():
        old = path.read_bytes()
        if old == data:
            return None
        # Only replace a byte-identical previously generated launcher with a
        # different installation path. Do not overwrite user customization.
        try:
            lines = old.decode('utf-8').splitlines()
            candidates = [json.loads(line[len('SKILL_PATH = '):]) for line in lines if line.startswith('SKILL_PATH = ')]
            if len(candidates) != 1 or not isinstance(candidates[0], str) or old != content(candidates[0]):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            raise ValueError('Existing .assets/ak.py differs; back it up and review before bootstrap') from None
    return path, data
