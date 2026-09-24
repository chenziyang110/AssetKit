#!/usr/bin/env python3
"""Build deterministic, allowlisted source/skill ZIPs and SHA-256 checksums."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES=('skills','.github','.claude-plugin','docs','tests','tools')
ROOT_FILES=('README.md','CHANGELOG.md','CONTRIBUTING.md','SECURITY.md','AGENTS.md','VERSION','.gitignore')


def version() -> str:
    value=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',value): raise ValueError('Stable release version must be MAJOR.MINOR.PATCH')
    skill=(ROOT/'skills/assetkit/SKILL.md').read_text(encoding='utf-8')
    if f'version: "{value}"' not in skill: raise ValueError('SKILL.md version differs from VERSION')
    marketplace=json.loads((ROOT/'.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
    if marketplace['metadata']['version']!=value: raise ValueError('Marketplace version differs from VERSION')
    return value


def source_files() -> list[Path]:
    files=[ROOT/p for p in ROOT_FILES if (ROOT/p).is_file()]
    for name in DIRECTORIES:
        for p in (ROOT/name).rglob('*'):
            if p.is_symlink(): raise ValueError('Distribution must be self-contained: '+str(p))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.pyo'}: files.append(p)
    return sorted(files)


def archive(path: Path, entries: list[tuple[Path,str]]) -> None:
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for source,name in sorted(entries,key=lambda item:item[1]):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.create_system=3; info.external_attr=0o100644<<16; info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,source.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)


def build(output: Path) -> dict:
    v=version(); output.mkdir(parents=True,exist_ok=True)
    files=source_files()
    whole=output/f'AssetKit-v{v}.zip'
    skill=output/f'assetkit-skill-v{v}.zip'
    archive(whole,[(p,'AssetKit/'+p.relative_to(ROOT).as_posix()) for p in files])
    base=ROOT/'skills/assetkit'
    archive(skill,[(p,'assetkit/'+p.relative_to(base).as_posix()) for p in files if base in p.parents])
    sums={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (whole,skill)}
    (output/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sums.items()),encoding='ascii')
    return {'version':v,'files':sums,'source_file_count':len(files)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'dist')
    args=p.parse_args()
    print(json.dumps(build(args.output.resolve()),indent=2))

if __name__=='__main__': main()
