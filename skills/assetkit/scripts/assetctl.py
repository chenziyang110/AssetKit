#!/usr/bin/env python3
"""AssetKit 1.0.0: local-first asset workflows for coding agents, Python 3.10+."""
from __future__ import annotations
import argparse
import contextlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
import ledger
import catalog
import profiles

FAST = {'detect','capture','find','resolve','scan','gate','doctor','backup'}
REQUEST_FIELDS = {'path','use','expect_revision','bundle','entry','snapshot','profile','type','domain','source_kind','source_ref','license','tags'}


def parser() -> argparse.ArgumentParser:
    p = ledger.parser()
    p.description = __doc__
    p._option_string_actions['--version'].version = catalog.VERSION
    p.add_argument('--pretty', action='store_true', help='Pretty JSON; compact JSON is the default')
    commands = next(a for a in p._actions if isinstance(a,argparse._SubParsersAction))
    d = commands.add_parser('detect',help='Read bounded manifest markers; do not initialize a ledger')
    d.add_argument('--depth',type=int,default=3)
    c = commands.add_parser('capture',help='Register a path in place; no full-card manifest required')
    c.add_argument('paths',nargs='*')
    c.add_argument('--batch',help='UTF-8 JSONL file, up to 100 small path/use requests')
    c.add_argument('--use',help='A short reuse purpose (<=120 characters); never inferred as a semantic fact')
    c.add_argument('--expect-revision',type=int)
    c.add_argument('--bundle',action='store_true')
    c.add_argument('--entry',help='Primary file relative to an explicitly grouped directory')
    c.add_argument('--snapshot',action='store_true')
    c.add_argument('--profile',choices=profiles.PROFILES)
    c.add_argument('--type',choices=sorted(ledger.KINDS))
    c.add_argument('--domain')
    c.add_argument('--source-kind',choices=['unknown','authored','generated','uploaded','imported'],default='unknown')
    c.add_argument('--source-ref')
    c.add_argument('--license')
    c.add_argument('--tag',dest='tags',action='append',default=[])
    c.add_argument('--hash-budget-mib',type=int,default=64,help='Total content-read budget for the call; 0 explicitly removes this cap')
    f = commands.add_parser('find',help='Bounded active-asset summaries from the derived index; no full-record scan on a warm cache')
    f.add_argument('query',nargs='?',default='')
    f.add_argument('--type',choices=sorted(ledger.KINDS))
    f.add_argument('--profile',choices=profiles.PROFILES)
    f.add_argument('--scope',default='.')
    f.add_argument('--match',choices=['any','all'],default='any')
    f.add_argument('--ready',action='store_true')
    f.add_argument('--fresh',action='store_true',help='Reconcile externally edited cards before querying')
    f.add_argument('--limit',type=int,default=5)
    f.add_argument('--offset',type=int,default=0)
    f.add_argument('--budget',type=int,default=4096,help='Maximum UTF-8 JSON bytes for results; not an LLM-token estimate')
    r = commands.add_parser('resolve',help='Get a usage contract, declared files, and native path/GUID hints')
    r.add_argument('id')
    r.add_argument('--intent',choices=['inspect','reuse'],default='inspect')
    r.add_argument('--verify',choices=['stat','hash'],default='stat')
    r.add_argument('--limit',type=int,default=5)
    r.add_argument('--offset',type=int,default=0)
    s = commands.add_parser('scan',help='Preview bounded inventory; --apply opts in to candidate registration')
    s.add_argument('--since',help='Compare working tree against a verified commit, e.g. HEAD')
    s.add_argument('--scope',default='.')
    s.add_argument('--limit',type=int,default=20)
    s.add_argument('--offset',type=int,default=0)
    s.add_argument('--apply',action='store_true')
    s.add_argument('--use')
    s.add_argument('--hash-budget-mib',type=int,default=64)
    g = commands.add_parser('gate',help='CI gate: missed registrations and stale/missing registered files')
    g.add_argument('--since',default='HEAD')
    g.add_argument('--ready',action='store_true',help='Also require ready state for changed asset candidates')
    h = commands.add_parser('doctor',help='Inspect configuration and SQLite health; --deep reconciles and checks records')
    h.add_argument('--deep',action='store_true')
    b = commands.add_parser('backup',help='Create a metadata-only ZIP without overwriting an existing backup')
    b.add_argument('--output',required=True)
    return p


def config(root: Path) -> dict:
    p = root/'.assets/config.json'
    if not p.exists(): ledger.fail('NOT_INITIALIZED: run bootstrap.py for this project first')
    value = ledger.read_json(p)
    if value.get('schema_version')!=1: ledger.fail('UNSUPPORTED_SCHEMA: do not downgrade or overwrite the existing ledger')
    uuid.UUID(value['project_id'])
    folders=value.get('managed_roots',[])
    if not isinstance(folders,list) or len(folders)>32: ledger.fail('INVALID_CONFIG: managed_roots must contain at most 32 directories')
    for folder in folders: ledger.local_path(root,folder)
    policy=value.get('discovery',{})
    if not isinstance(policy,dict) or set(policy)-{'roots','extensions','exclude_globs'}: ledger.fail('INVALID_CONFIG: unknown discovery policy')
    roots=policy.get('roots',['.'])
    if not isinstance(roots,list) or not 1<=len(roots)<=32: ledger.fail('INVALID_CONFIG: discovery.roots must contain 1..32 scopes')
    for folder in roots:
        if folder!='.': ledger.local_path(root,folder)
    extensions=policy.get('extensions',{})
    if not isinstance(extensions,dict) or len(extensions)>100: ledger.fail('INVALID_CONFIG: invalid extension map')
    for ext,kind in extensions.items():
        if not re.fullmatch(r'\.[a-z0-9]+',ext) or kind not in ledger.KINDS: ledger.fail('INVALID_CONFIG: invalid extension/type')
    ledger.text_list(policy.get('exclude_globs',[]),'discovery.exclude_globs',100,200)
    return value


def requests(args: argparse.Namespace) -> list[dict]:
    if args.batch and args.paths: ledger.fail('Use paths or --batch, not both')
    if args.batch:
        p=Path(args.batch)
        if p.stat().st_size>512*1024: ledger.fail('BATCH_LIMIT: request file exceeds 512 KiB')
        values=[json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]
    else:
        defaults={k:v for k,v in vars(args).items() if k in REQUEST_FIELDS and v is not None}
        values=[{**defaults,'path':path} for path in args.paths]
    for v in values:
        if not isinstance(v,dict) or set(v)-REQUEST_FIELDS: ledger.fail('INVALID_REQUEST: unknown capture request fields')
        ledger.text(v.get('path'),'path',1000)
        for field in ('bundle','snapshot'):
            if field in v and type(v[field]) is not bool: ledger.fail('INVALID_REQUEST: '+field+' must be boolean')
        if v.get('profile') and v['profile'] not in profiles.PROFILES: ledger.fail('INVALID_PROFILE')
        if 'expect_revision' in v and (type(v['expect_revision']) is not int or v['expect_revision']<1): ledger.fail('INVALID_REVISION')
    return values


def legacy(root: Path, args: argparse.Namespace) -> dict:
    """Keep v0.3 commands and card schema compatible, with stricter path preflight."""
    catalog.guard(root,records=True)
    if args.command!='init': config(root)
    cards=[]
    if args.command=='add':
        request=ledger.read_json(Path(args.manifest))
        for f in request.get('files',[]): catalog.safe_file(root,f['path'])
    elif args.command in {'show','patch','refresh'}:
        cards=[catalog.load(root,args.id)]
    elif args.command in {'validate','sync','reindex','search'}:
        cards=[catalog.load(root,p.stem) for p in (root/'.assets/records').glob('*.json')]
    for card in cards:
        for f in card['files']: catalog.safe_file(root,f['path'])
    # Legacy reconciliation can change the shared index. Invalidate the fast
    # auxiliary index first; recovery always derives from authoritative cards.
    if args.command not in {'init','show','validate'}: catalog.dirty(root)
    return ledger.execute(args)


def execute(args: argparse.Namespace) -> dict:
    root=Path(args.root).expanduser().resolve()
    catalog.guard(root)
    if args.command=='detect':
        if not 0<=args.depth<=5: ledger.fail('DETECTION_LIMIT: depth must be 0..5')
        return {'ok':True,'projects':profiles.detect(root,args.depth),'version':catalog.VERSION,
                'scope':'manifest/path recognition; not an engine runtime compatibility certification'}
    if args.command not in FAST: return legacy(root,args)
    with ledger.project_lock(root):
        cfg=config(root)
        if args.command=='resolve': return catalog.resolve(root,catalog.load(root,args.id),args)
        if args.command=='backup':
            catalog.guard(root,records=True)
            return catalog.backup(root,args.output)
        with contextlib.closing(ledger.connect(root)) as conn:
            info=catalog.ensure(root,conn,fresh=getattr(args,'fresh',False) or args.command=='gate' or getattr(args,'deep',False))
            if args.command=='capture': result=catalog.capture(root,conn,cfg,requests(args),args.hash_budget_mib)
            elif args.command=='find': result=catalog.find(conn,args)
            elif args.command=='scan': result=catalog.scan(root,conn,cfg,args)
            elif args.command=='gate': result=catalog.gate(root,conn,args,cfg)
            elif args.command=='doctor':
                integrity=conn.execute('PRAGMA quick_check').fetchone()[0]
                counts=[dict(r) for r in conn.execute('SELECT type,status,count(*) AS count FROM cards GROUP BY type,status')]
                result={'ok':integrity=='ok','version':catalog.VERSION,'schema_version':1,'sqlite':integrity,'counts':counts,
                        'consistency':'local advisory lock; run sync at task start/after merges; find --fresh after manual in-place card edits',
                        'deployment':'local filesystem, Git working copies; not a multi-host database service'}
            else: ledger.fail('Unknown command')
            result['index']=info
            return result


def main() -> int:
    started=time.perf_counter()
    try:
        args=parser().parse_args()
        result=execute(args)
        if args.command=='find':
            if not 1024<=args.budget<=65536: ledger.fail('OUTPUT_BUDGET: choose 1024..65536 bytes')
            while len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>args.budget and result['items']:
                result['items'].pop()
                result['next_offset']=args.offset+len(result['items'])
            if result['total']>args.offset and not result['items']:
                ledger.fail('OUTPUT_BUDGET: one result exceeds the budget; increase --budget')
        # Pretty rendering is opt-in and is not covered by find's compact-byte budget.
        print(json.dumps(result,ensure_ascii=False,indent=2 if args.pretty else None))
        return 0 if result.get('ok') else 1
    except (ledger.AssetError,OSError,ValueError,KeyError,TypeError,sqlite3.Error,subprocess.SubprocessError) as exc:
        message=str(exc)
        match=re.match(r'^([A-Z_]+):',message)
        code=match[1] if match else ('INDEX_ERROR' if isinstance(exc,sqlite3.Error) else 'ASSET_ERROR')
        print(json.dumps({'ok':False,'code':code,'error':message[:1000],
                          'next':'reindex rebuilds a corrupt derived index without changing source cards' if code=='INDEX_ERROR' else 'correct the input or inspect the affected record',
                          'elapsed_ms':round((time.perf_counter()-started)*1000,2)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
