"""AssetKit stable workflows. Files/JSON cards are authoritative; SQLite is derived.

Only a trusted local working tree is supported. The advisory lock coordinates
AssetKit writers, not editors, hostile processes, network filesystems or machines.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid
import zipfile

import ledger as db
import profiles

VERSION = '1.0.0'
DDL = '''
CREATE TABLE IF NOT EXISTS assetkit_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assetkit_files(
 asset_id TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(asset_id,path));
CREATE INDEX IF NOT EXISTS assetkit_path ON assetkit_files(path);
CREATE INDEX IF NOT EXISTS assetkit_hash ON assetkit_files(sha256);
'''


def guard(root: Path, records: bool = False) -> None:
    source = Path(__file__).resolve().parent.parent
    if root == source or source in root.parents:
        db.fail('UNSAFE_ROOT: project data cannot live inside the installed skill')
    if not root.is_dir(): db.fail('Project root must already exist')
    for rel in ('.assets','.assets/records','.assets/cache','.assets/.lock','.assets/config.json',
                '.assets/cache/catalog.sqlite','.assets/cache/catalog.sqlite-journal',
                '.assets/cache/catalog.sqlite-wal','.assets/cache/catalog.sqlite-shm', '.assets/cache/.dirty'):
        target=root/rel
        if target.is_symlink() or target.resolve()!=target: db.fail('UNSAFE_METADATA: symbolic link or redirected path: '+rel)
    if records and (root/'.assets/records').exists():
        for p in (root/'.assets/records').iterdir():
            if p.is_symlink(): db.fail('UNSAFE_METADATA: linked record: '+p.name)


def safe_file(root: Path, value: str) -> Path:
    p = db.local_path(root, value)
    if not profiles.allowed(value): db.fail('EXCLUDED_ASSET: secret, generated, or tool-owned path: '+value)
    q = p
    while q != root:
        if q.is_symlink(): db.fail('UNSAFE_ASSET: symbolic links are not followed: '+value)
        q = q.parent
    return p


def load(root: Path, asset_id: str) -> dict:
    p = db.card_path(root, asset_id)
    if p.is_symlink(): db.fail('UNSAFE_METADATA: linked record')
    card = db.read_json(p)
    db.valid_card(root, card)
    if card['id'] != asset_id: db.fail('CORRUPT_CARD: id does not match filename')
    project=card['source'].get('project')
    if project is not None and (not isinstance(project,dict) or project.get('profile') not in profiles.PROFILES):
        db.fail('CORRUPT_CARD: invalid source.project context')
    for f in card['files']:
        stats=f.get('stat')
        if stats is not None and (not isinstance(stats,dict) or set(stats)!={'size','mtime_ns','ctime_ns','device','inode'} or any(type(v) is not int for v in stats.values())):
            db.fail('CORRUPT_CARD: invalid optional stat signature')
    return card


def signature(p: Path) -> dict:
    s = p.stat()
    return {'size':s.st_size, 'mtime_ns':s.st_mtime_ns, 'ctime_ns':s.st_ctime_ns,
            'device':s.st_dev, 'inode':s.st_ino}


def dirty(root: Path) -> None:
    (root/'.assets/cache').mkdir(parents=True, exist_ok=True)
    marker = root/'.assets/cache/.dirty'
    with marker.open('wb') as f:
        f.write(b'pending\n'); f.flush(); os.fsync(f.fileno())


def generation(root: Path) -> str:
    records = root/'.assets/records'
    s = records.stat()
    # Cheap signals catch atomic record writes and Git checkout. Manual in-place
    # edits during a session require sync/--fresh; cached search does not promise
    # a distributed or filesystem-watch consistency model.
    try:
        head = profiles.git(root, ['rev-parse','--verify','HEAD'], 4096).decode().strip()
    except (ValueError, OSError): head = 'no-commit'
    return json.dumps([s.st_mtime_ns, s.st_ctime_ns, head])


def index_files(conn: sqlite3.Connection, card: dict) -> None:
    conn.execute('DELETE FROM assetkit_files WHERE asset_id=?', (card['id'],))
    conn.executemany('INSERT INTO assetkit_files VALUES(?,?,?)',
                     [(card['id'],f['path'],f['sha256']) for f in card['files']])


def mark_clean(root: Path, conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute('INSERT OR REPLACE INTO assetkit_meta VALUES(?,?)', ('generation', generation(root)))
    (root/'.assets/cache/.dirty').unlink(missing_ok=True)


def ensure(root: Path, conn: sqlite3.Connection, fresh: bool = False) -> dict:
    conn.executescript(DDL)
    old = conn.execute("SELECT value FROM assetkit_meta WHERE key='generation'").fetchone()
    if not fresh and old and old[0] == generation(root) and not (root/'.assets/cache/.dirty').exists():
        return {'reconciled':False,'record_files_read':0}
    guard(root, records=True)
    # Crash recovery or explicit reconciliation; source records remain authoritative.
    synchronized = db.sync_index(root, conn)
    with conn:
        conn.execute('DELETE FROM assetkit_files')
        for row in conn.execute('SELECT body FROM cards'):
            index_files(conn, json.loads(row[0]))
    mark_clean(root, conn)
    return {'reconciled':True, **synchronized}


def persist(root: Path, conn: sqlite3.Connection, card: dict) -> None:
    db.valid_card(root, card)
    dirty(root)
    db.write_card(root, conn, card)
    with conn: index_files(conn, card)
    mark_clean(root, conn)


def members(root: Path, path: str, bundle: bool, entry: str | None) -> list[dict]:
    p = safe_file(root, path)
    if not p.exists(): db.fail('MISSING_ASSET: '+path)
    if p.is_dir():
        if not bundle and p.suffix.lower() not in profiles.BUNDLES:
            db.fail('BUNDLE_REQUIRED: use --bundle for an explicit reusable directory, not a whole project')
        paths = []
        visited=0
        for directory, dirs, files in os.walk(p, followlinks=False):
            d = Path(directory)
            visited+=len(dirs)+len(files)
            if visited>4096: db.fail('BUNDLE_LIMIT: more than 4096 directory entries')
            for name in dirs + files:
                relative = (d/name).relative_to(root).as_posix()
                safe_file(root, relative)
            for name in sorted(files):
                paths.append((d/name).relative_to(root).as_posix())
                if len(paths)>128: db.fail('BUNDLE_LIMIT: over 128 files; register a versioned entry/manifest instead')
        paths.sort()
        if not paths: db.fail('EMPTY_BUNDLE')
        preferred = (p/entry).relative_to(root).as_posix() if entry else None
        if entry and preferred not in paths: db.fail('BAD_ENTRY: --entry must select a file inside the bundle')
        primary = preferred or next((v for v in paths if Path(v).name in {'Contents.json','manifest.json','config.json','model.safetensors.index.json'}),paths[0])
        paths.remove(primary); paths.insert(0, primary)
    else:
        if not p.is_file(): db.fail('NOT_A_REGULAR_FILE: '+path)
        if p.suffix in {'.meta','.import','.uid'}: db.fail('SIDECAR: capture the primary asset instead')
        paths = [path]
        if p.suffix.lower()=='.gltf':
            if p.stat().st_size>65536: db.fail('MANIFEST_LIMIT: glTF JSON over 64 KiB; use an explicit bounded bundle')
            data=json.loads(profiles.head(p))
            for section in ('buffers','images'):
                for item in data.get(section,[]):
                    uri=item.get('uri')
                    if not uri or uri.startswith('data:'): continue
                    from urllib.parse import unquote, urlsplit
                    parsed=urlsplit(uri)
                    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment: db.fail('EXTERNAL_DEPENDENCY: glTF requires an external URI; materialize a reviewed bundle')
                    relative=Path(os.path.normpath(p.parent/unquote(parsed.path))).relative_to(root).as_posix()
                    safe_file(root,relative)
                    if relative not in paths: paths.append(relative)
                    if len(paths)>128: db.fail('BUNDLE_LIMIT: over 128 direct glTF dependencies')
        ctx = profiles.context(root, path)
        suffixes = ['.meta'] if ctx['profile']=='unity' else (['.import','.uid'] if ctx['profile']=='godot' else [])
        for suffix in suffixes:
            sidecar = path+suffix
            if (root/sidecar).exists():
                safe_file(root, sidecar); paths.append(sidecar)
    return [{'path':v,'role':'primary' if i==0 else 'dependency'} for i,v in enumerate(paths)]


def capture_one(root: Path, conn: sqlite3.Connection, config: dict, request: dict, budget: list[int]) -> dict:
    path = request['path']
    safe_file(root, path)
    files = members(root,path,request.get('bundle',False),request.get('entry'))
    known = conn.execute('SELECT DISTINCT cards.body FROM cards JOIN assetkit_files ON cards.id=assetkit_files.asset_id '
                         'WHERE assetkit_files.path=? AND cards.status NOT IN (?,?) ORDER BY cards.content_version DESC',
                         (files[0]['path'],'archived','deprecated')).fetchall()
    if len(known)>1: db.fail('AMBIGUOUS_PATH: multiple active records; select an id with the legacy patch/refresh commands')
    old = load(root,json.loads(known[0][0])['id']) if known else None
    purpose = request.get('use')
    if purpose is not None: db.text(purpose,'use',120)
    expected = request.get('expect_revision')
    if expected is not None and (not old or old['revision']!=expected): db.fail('REVISION_CONFLICT: inspect current id/revision')
    same = old and {f['path'] for f in files} == {f['path'] for f in old['files']}
    if same:
        same = all(f.get('stat') == signature(safe_file(root,f['path'])) for f in old['files'])
    metadata_change = old and ((purpose is not None and purpose != old['summary']) or
                     (request.get('source_kind','unknown') != 'unknown' and (request.get('source_kind') != old['source']['kind'] or request.get('source_ref') != old['source'].get('ref'))) or
                     (request.get('license') and request['license'] != old['rights'].get('license')) or
                     any(tag not in old.get('tags',[]) for tag in request.get('tags',[])))
    if same and not metadata_change:
        return {**db.result_card(old),'action':'unchanged','bytes_hashed':0}
    if old and expected is None:
        return {'ok':False,'id':old['id'],'revision':old['revision'],'code':'REVISION_REQUIRED',
                'next':'capture this path with --expect-revision '+str(old['revision'])}
    if old and old.get('content_mode','snapshot')!='live': db.fail('IMMUTABLE_SNAPSHOT: create a new version at a different path')
    size = sum(safe_file(root,f['path']).stat().st_size for f in files)
    if budget[0]>=0 and size>budget[0]: db.fail('HASH_BUDGET: use a manifest/index entry or explicitly raise --hash-budget-mib; no asset was read')
    if budget[0]>=0: budget[0]-=size
    inspected = []
    for f in files:
        before = signature(safe_file(root,f['path']))
        actual = db.inspect_file(root,f)
        if signature(root/f['path']) != before: db.fail('CONTENT_RACE: file changed during capture')
        actual['stat'] = before
        inspected.append(actual)
    if old:
        card = dict(old)
        card.update(revision=old['revision']+1, updated_at=db.stamp(), status='candidate',files=inspected)
        if purpose:
            card['summary']=purpose; card['use_when']=[purpose]
        card.pop('reviewed_by',None); card.pop('review_evidence',None)
    else:
        ctx = profiles.context(root,path,request.get('profile'))
        stem = Path(path).stem
        slug = re.sub(r'[^a-z0-9]+','-',stem.lower()).strip('-')[:60] or 'asset'
        key_hash = hashlib.sha256(path.encode()).hexdigest()[:12]
        request_key = 'capture:'+hashlib.sha256(path.encode()).hexdigest()
        asset_id = 'ast_'+uuid.uuid5(uuid.UUID(config['project_id']),request_key).hex
        if db.card_path(root,asset_id).exists(): db.fail('INACTIVE_RECORD: this path has an archived/deprecated record; review it explicitly')
        card = {'schema_version':1,'id':asset_id,'revision':1, 'logical_key':f"{ctx['profile']}/{slug}-{key_hash}",
                'content_mode':'snapshot' if request.get('snapshot') else 'live', 'content_version':1 if request.get('snapshot') else 0,
                'type':request.get('type') or profiles.kind(path,config.get('discovery',{}).get('extensions')) or 'other','domain':request.get('domain') or ctx['profile'],
                'title':Path(path).name[:100], 'summary':purpose or ('Indexed file: '+Path(path).name)[:240],
                'use_when':[purpose or 'Inspect this indexed asset; semantic purpose has not been supplied'],
                'status':'candidate','storage_policy':'in-place','files':inspected,
                'tags':['profile:'+ctx['profile'],'kind:'+profiles.NATIVE.get(Path(path).suffix.lower(), profiles.kind(path) or 'bundle')],
                'source':{'kind':'unknown','ref':'unknown','project':ctx},
                'rights':{'status':'unknown','license':'unknown'},'restrictions':[],
                'created_at':db.stamp(),'updated_at':db.stamp(),'request_key':request_key,'request_fingerprint':'pending'}
    if request.get('source_kind','unknown')!='unknown':
        if not request.get('source_ref'): db.fail('SOURCE_REQUIRED: --source-ref must accompany a known source kind')
        card['source'] = {**card['source'],'kind':request['source_kind'],'ref':request['source_ref']}
    if request.get('license'):
        card['rights']={'status':'restricted','license':request['license'],'note':'Recorded assertion; review before distribution'}
    card['tags']=list(dict.fromkeys([*card.get('tags',[]),*request.get('tags',[])]))
    card['request_fingerprint']=hashlib.sha256(db.encoded({k:v for k,v in card.items() if k not in db.SYSTEM})).hexdigest()
    db.valid_card(root,card)
    for f in files:
        if signature(root/f['path']) != next(v['stat'] for v in inspected if v['path']==f['path']):
            db.fail('CONTENT_RACE: asset changed before record commit')
    duplicates = conn.execute('SELECT DISTINCT asset_id FROM assetkit_files WHERE sha256=? AND asset_id!=? LIMIT 5',
                              (inspected[0]['sha256'],card['id'])).fetchall()
    persist(root,conn,card)
    return {**db.result_card(card),'action':'updated' if old else 'created','path':files[0]['path'],
            'bytes_hashed':size,'same_content_ids':[v[0] for v in duplicates]}


def capture(root: Path, conn: sqlite3.Connection, config: dict, requests: list[dict], mib: int) -> dict:
    if not 1<=len(requests)<=100: db.fail('BATCH_LIMIT: 1 to 100 requests per call')
    if mib<0: db.fail('hash-budget-mib must be non-negative; zero explicitly means unlimited')
    budget=[mib*1024*1024 if mib else -1]
    items=[]
    for req in requests:
        try: items.append(capture_one(root,conn,config,req,budget))
        except (db.AssetError,OSError,ValueError,KeyError,TypeError) as exc:
            items.append({'ok':False,'path':str(req.get('path',''))[:500],'error':str(exc)[:500]})
    errors=sum(not x['ok'] for x in items)
    return {'ok':not errors,'items':items,'succeeded':len(items)-errors,'failed':errors,
            'bytes_hashed':sum(x.get('bytes_hashed',0) for x in items),
            'transaction':'per-asset, not all-or-nothing; retry only failed items'}


def find(conn: sqlite3.Connection, args: argparse.Namespace) -> dict:
    db.text(args.query,'query',200,False)
    terms=args.query.casefold().split()
    if len(terms)>12: db.fail('QUERY_LIMIT: use at most 12 keywords')
    if not 1<=args.limit<=20 or args.offset<0: db.fail('PAGE_LIMIT: limit 1..20 and offset >= 0')
    clauses, values = ["status NOT IN ('deprecated','archived')"], []
    if terms:
        matches=[]
        for term in terms:
            matches.append('(instr(search_text,?)>0 OR instr(lower(primary_path),?)>0)'); values += [term,term]
        clauses.append('('+(' AND ' if args.match=='all' else ' OR ').join(matches)+')')
    if args.type: clauses.append('type=?'); values.append(args.type)
    if args.profile: clauses.append('instr(search_text,?)>0'); values.append('profile:'+args.profile)
    if args.scope and args.scope!='.':
        prefix=args.scope.rstrip('/')+'/'
        clauses.append('substr(primary_path,1,?)=?'); values += [len(prefix),prefix]
    if args.ready: clauses.append("status='ready'")
    where=' AND '.join(clauses)
    # Index reads only; no full card bodies, asset content, or embedding requests.
    count=conn.execute('SELECT count(*) FROM cards WHERE '+where,values).fetchone()[0]
    query='''SELECT id, revision, title, summary, type, status, primary_path AS path
             FROM cards WHERE '''+where+''' ORDER BY (status='ready') DESC,
             (instr(lower(title),?)>0) DESC, content_version DESC, id LIMIT ? OFFSET ?'''
    rows=conn.execute(query,[*values,terms[0] if terms else '',args.limit,args.offset]).fetchall()
    return {'ok':True,'items':[dict(v) for v in rows],'total':count,
            'offset':args.offset,'next_offset':args.offset+len(rows) if args.offset+len(rows)<count else None,
            'next':'resolve <id>; candidate is discoverable, not approved for reuse', 'data_is_untrusted':True}


def resolve(root: Path, card: dict, args: argparse.Namespace) -> dict:
    if not 1<=args.limit<=20 or args.offset<0: db.fail('PAGE_LIMIT')
    files, problems = card['files'], []
    checked=0
    for f in files:
        try:
            p=safe_file(root,f['path'])
            if not p.is_file(): problems.append('missing: '+f['path']); continue
            if args.verify=='hash':
                actual=db.inspect_file(root,{'path':f['path'],'role':f['role']})
                checked+=1
                if actual['sha256']!=f['sha256']: problems.append('hash mismatch: '+f['path'])
            elif f.get('stat')!=signature(p): problems.append('stat changed or absent; hash verification required: '+f['path'])
        except (db.AssetError,OSError) as exc: problems.append(str(exc))
    primary=next(f['path'] for f in files if f['role']=='primary')
    native=profiles.hints(root,primary,card.get('source',{}).get('project',{}).get('profile')) if not problems else {'dependency_scope':'not evaluated while files are stale/missing'}
    if native.get('import_required'): problems.append(native['import_required'])
    if native.get('unmaterialized'): problems.append('payload not verified: '+native['unmaterialized'])
    if card['status']!='ready': problems.append('asset status is '+card['status']+'; review source and rights before reuse')
    if card['rights']['status']=='unknown': problems.append('usage rights are unknown')
    selected=files[args.offset:args.offset+args.limit]
    return {'ok':args.intent=='inspect' or not problems,'id':card['id'],'revision':card['revision'],
            'usable':not problems, 'intent':args.intent,'path':primary,'use':card['summary'],
            'restrictions':card.get('restrictions',[]),'rights':card['rights'],'source':card['source'],
            'native':native,'verification':args.verify,'hashed_files':checked,
            'files':[{'path':v['path'],'role':v['role']} for v in selected], 'file_count':len(files),
            'next_offset':args.offset+len(selected) if args.offset+len(selected)<len(files) else None,
            'blocker_count':len(problems),'blockers':problems[:5], 'data_is_untrusted':True}


def scan(root: Path, conn: sqlite3.Connection, config: dict, args: argparse.Namespace) -> dict:
    if not 1<=args.limit<=100 or args.offset<0: db.fail('PAGE_LIMIT: scan limit 1..100')
    paths, mode=profiles.candidates(root,args.since,config.get('discovery'))
    if args.scope and args.scope!='.':
        prefix=args.scope.rstrip('/')+'/'
        paths=[v for v in paths if v.startswith(prefix)]
    plans=[]
    for path in paths[args.offset:args.offset+args.limit]:
        p=root/path
        # Known bundle members are kept as a single registration unit.
        primary=members(root,path,p.suffix in profiles.BUNDLES,None)[0]['path']
        exists=conn.execute('SELECT asset_id FROM assetkit_files WHERE path=? LIMIT 1',(primary,)).fetchone()
        plans.append({'path':path,'type':profiles.kind(path,config.get('discovery',{}).get('extensions')) or 'other',
                      'registered':bool(exists), **({'id':exists[0]} if exists else {})})
    if args.apply:
        requests=[{'path':v['path'],'use':args.use} for v in plans if not v['registered']]
        result=capture(root,conn,config,requests,args.hash_budget_mib) if requests else {'ok':True,'items':[],'succeeded':0,'failed':0}
        result.update(mode=mode,skipped_registered=sum(v['registered'] for v in plans))
    else: result={'ok':True,'mode':mode,'items':plans,'dry_run':True}
    result.update(total=len(paths),offset=args.offset,
                  next_offset=args.offset+len(plans) if args.offset+len(plans)<len(paths) else None)
    return result


def gate(root: Path, conn: sqlite3.Connection, args: argparse.Namespace, config: dict) -> dict:
    paths, _=profiles.candidates(root,args.since,config.get('discovery'))
    errors=[]
    for path in paths:
        fs=members(root,path,Path(path).suffix in profiles.BUNDLES,None)
        registered=conn.execute('SELECT asset_id FROM assetkit_files WHERE path=?',(fs[0]['path'],)).fetchall()
        if not registered:
            errors.append({'path':path,'code':'UNREGISTERED'})
        elif args.ready:
            for row in registered:
                card=load(root,row[0])
                if card['status']!='ready': errors.append({'id':row[0],'path':path,'code':'NOT_READY'})
                native=profiles.hints(root,fs[0]['path'])
                if native.get('unmaterialized') or native.get('import_required'):
                    errors.append({'id':row[0],'path':path,'code':'PAYLOAD_OR_IMPORT_REQUIRED'})
    # Also check registered files changed/deleted, including sidecars and files
    # which classification would not discover. This is metadata stat I/O only
    # until a difference is observed; content verification is streamed.
    checked=0
    for row in conn.execute('SELECT body FROM cards WHERE status NOT IN (?,?)',('archived','deprecated')):
        card=json.loads(row[0])
        changed=False
        for f in card['files']:
            p=safe_file(root,f['path'])
            if not p.is_file():
                errors.append({'id':card['id'],'path':f['path'],'code':'MISSING'}); changed=True
            elif f.get('stat')!=signature(p):
                checked+=1
                if db.inspect_file(root,{'path':f['path'],'role':f['role']})['sha256']!=f['sha256']:
                    changed=True
                    errors.append({'id':card['id'],'path':f['path'],'code':'STALE_CONTENT'})
        if args.ready and changed and card['status']!='ready': errors.append({'id':card['id'],'code':'NOT_READY'})
    return {'ok':not errors,'error_count':len(errors),'errors':errors[:20],'truncated':len(errors)>20,
            'hashed_files':checked,'scope':'new/modified Git asset candidates plus registered file integrity; no engine dependency validation'}


def backup(root: Path, output: str) -> dict:
    path=Path(output).expanduser().resolve()
    if path.exists(): db.fail('BACKUP_EXISTS: refusing to overwrite')
    if root/'.assets'==path or root/'.assets' in path.parents: db.fail('UNSAFE_BACKUP: choose a destination outside .assets')
    records=list((root/'.assets/records').glob('*.json'))
    for p in records: load(root,p.stem)
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as z:
            for p in [root/'.assets/config.json',*records]: z.write(p,p.relative_to(root).as_posix())
    except Exception:
        path.unlink(missing_ok=True); raise
    return {'ok':True,'path':str(path),'records':len(records),'includes':'metadata only; back up source assets separately'}
