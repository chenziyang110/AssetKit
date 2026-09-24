#!/usr/bin/env python3
"""Small agent-facing commands; full v1 assetctl contracts remain available.

Compact output is a projection, not lossy compression of safety information.
No full-result caching, session-memory assumptions, hosted APIs or tokenizers.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
import assetctl
import catalog
import ledger as db
import verification

MAX_RECEIPT = 1024 * 1024


def wire(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        db.fail('BAD_ARGUMENT: ' + message)


def parser() -> argparse.ArgumentParser:
    p = Parser(description=__doc__)
    p.add_argument('--root', default='.')
    p.add_argument('--version', action='version', version=catalog.VERSION)
    subs = p.add_subparsers(dest='command', required=True)
    for name in ('find', 'get'):
        q = subs.add_parser(name, help='Small candidates with usage checks' if name == 'find' else 'One asset or selected metadata')
        q.add_argument('query' if name == 'find' else 'ref')
        q.add_argument('--budget', type=int, default=2048, help='UTF-8 JSON bytes, not provider tokens')
        q.add_argument('--fresh', action='store_true')
        q.add_argument('--verify', choices=['auto', 'hash', 'stat'], default='auto')
        q.add_argument('--hash-budget-mib', type=int, default=64)
        if name == 'find':
            q.add_argument('--limit', type=int, default=3)
            q.add_argument('--offset', type=int, default=0)
            q.add_argument('--scope', default='.')
            q.add_argument('--type', choices=sorted(db.KINDS))
            q.add_argument('--profile', choices=assetctl.profiles.PROFILES)
            q.add_argument('--match', choices=['any', 'all'], default='any')
            q.add_argument('--ready', action='store_true')
            q.add_argument('--summaries', action='store_true', help='Cheapest candidate discovery; never authorizes reuse')
        else:
            q.add_argument('--fields', help='Read only named card fields; not a reuse check')
    # Reuse the proven input contract instead of creating another batch schema.
    old = next(a for a in assetctl.parser()._actions if isinstance(a, argparse._SubParsersAction))
    put = subs.add_parser('put', parents=[old.choices['capture']], add_help=False,
                          help='Path + purpose; batch accepts a file or stdin (-)')
    put.add_argument('--budget', type=int, default=1024)
    put.add_argument('--details', action='store_true', help='Return every receipt item when it fits the budget')
    check = subs.add_parser('check', help='One commit gate, not one validation per new file')
    check.add_argument('--since', default='HEAD')
    check.add_argument('--ready', action='store_true')
    check.add_argument('--budget', type=int, default=1024)
    receipt = subs.add_parser('receipt', help='Page historical batch/check results; never a fresh reuse authorization')
    receipt.add_argument('ref')
    receipt.add_argument('--offset', type=int, default=0)
    receipt.add_argument('--limit', type=int, default=5)
    receipt.add_argument('--budget', type=int, default=2048)
    return p


def short_ref(conn: sqlite3.Connection, asset_id: str) -> str:
    """No sequential session handles: prefixes survive context loss/reindex."""
    for length in (8, 12, 16, 24, 32):
        prefix = asset_id[:4 + length]
        matches = conn.execute('SELECT id FROM cards WHERE id>=? AND id<? LIMIT 2',
                               (prefix, prefix + 'g')).fetchall()
        if len(matches) == 1 and matches[0][0] == asset_id:
            return '@' + asset_id[4:4 + length]
    return asset_id


def identify(root: Path, conn: sqlite3.Connection, value: str) -> str:
    if re.fullmatch(r'ast_[0-9a-f]{32}', value):
        return value
    if re.fullmatch(r'@[0-9a-f]{8,32}', value):
        prefix = 'ast_' + value[1:]
        rows = conn.execute('SELECT id FROM cards WHERE id>=? AND id<? LIMIT 2',
                            (prefix, prefix + 'g')).fetchall()
    else:
        catalog.safe_file(root, value)
        rows = conn.execute("SELECT DISTINCT cards.id FROM cards JOIN assetkit_files ON cards.id=assetkit_files.asset_id "
                            "WHERE path=? AND status NOT IN ('deprecated','archived') LIMIT 2", (value,)).fetchall()
    if not rows:
        db.fail('NOT_FOUND: find by purpose or use the full asset ID')
    if len(rows) != 1:
        db.fail('AMBIGUOUS_REF: use the full asset ID; no match was selected')
    return rows[0][0]


def small_issue(conn: sqlite3.Connection, issue: dict, owner: str | None = None) -> dict:
    result = {'code': issue['code']}
    if issue.get('id') and issue['id'] != owner:
        result['ref'] = short_ref(conn, issue['id'])
    if issue.get('path'):
        result['path'] = issue['path']
    return result


def brief(root: Path, conn: sqlite3.Connection, card: dict, args: argparse.Namespace,
          budget: list[int]) -> dict:
    result = verification.evaluate(root, card, args.verify, budget, conn)
    primary = next(f['path'] for f in card['files'] if f['role'] == 'primary')
    out = {'ref': short_ref(conn, card['id']), 'rev': card['revision'], 'path': primary,
           'use': card['summary'], 'usable': result['usable']}
    if not result['usable']:
        out['blocked'] = [small_issue(conn, v, card['id']) for v in result['issues'][:3]]
        if result['issue_count'] > 3:
            out['blocker_count'] = result['issue_count']
    # Never omit rights notes or constraints, even when they make a row large.
    rights = card['rights']
    if rights['status'] != 'unknown':
        out['rights'] = rights
    if card.get('restrictions'):
        out['restrictions'] = card['restrictions']
    if result['native'].get('native_ref'):
        out['native'] = result['native']['native_ref']
    if len(card['files']) > 1:
        out['file_count'] = len(card['files'])
    dependencies = result['nodes'][1:]
    if dependencies:
        out['dependencies'] = [
            {'ref': short_ref(conn, node['id']), 'rights': node['rights'],
             **({'restrictions': node['restrictions']} if node.get('restrictions') else {})}
            for node in dependencies]
    return out


def _receipt_dir(root: Path) -> Path:
    path = root / '.assets/cache/receipts'
    if path.is_symlink() or path.resolve() != path:
        db.fail('UNSAFE_METADATA: linked receipts directory')
    return path


def save_receipt(root: Path, items: list[dict], kind: str) -> str:
    # Durable enough to page after a tool response, but never an authority/cache
    # for current readiness. Pruned local results can be absent after reindex.
    value = {'kind': kind, 'items': items}
    data = wire(value).encode('utf-8')
    if len(data) > MAX_RECEIPT:
        db.fail('RECEIPT_LIMIT: results exceeded 1 MiB; use smaller batches')
    digest = hashlib.sha256(data).hexdigest()
    directory = _receipt_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (digest + '.json')
    if path.is_symlink():
        db.fail('UNSAFE_METADATA: linked receipt')
    if path.exists():
        if path.read_bytes() != data:
            db.fail('CORRUPT_RECEIPT: content digest mismatch')
    else:
        from install import atomic_write
        atomic_write(path, data)
    candidates = sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for old in candidates[128:]:
        if old != path:
            if old.is_symlink():
                db.fail('UNSAFE_METADATA: linked receipt')
            old.unlink()
    for length in (16, 24, 32, 64):
        if len(list(directory.glob(digest[:length] + '*.json'))) == 1:
            return digest[:length]
    return digest


def page_receipt(root: Path, args: argparse.Namespace) -> dict:
    if not re.fullmatch(r'[0-9a-f]{16,64}', args.ref):
        db.fail('BAD_RECEIPT: use the returned receipt handle')
    if not 1 <= args.limit <= 100 or args.offset < 0:
        db.fail('PAGE_LIMIT: limit 1..100 and offset >= 0')
    files = list(_receipt_dir(root).glob(args.ref + '*.json'))
    if len(files) != 1:
        db.fail('RECEIPT_UNAVAILABLE: absent or ambiguous; inspect current assets, do not replay writes blindly')
    p = files[0]
    if p.is_symlink() or p.stat().st_size > MAX_RECEIPT:
        db.fail('UNSAFE_METADATA: invalid receipt file')
    data = p.read_bytes()
    if hashlib.sha256(data).hexdigest() != p.stem:
        db.fail('CORRUPT_RECEIPT: content digest mismatch')
    value = json.loads(data)
    rows = value['items']
    out = {'ok': True, 'historical': True, 'items': rows[args.offset:args.offset + args.limit]}
    while len(wire(out).encode()) + 50 > args.budget and out['items']:
        out['items'].pop()
    if not out['items'] and args.offset < len(rows):
        db.fail('OUTPUT_BUDGET: increase --budget to read one complete receipt item')
    cursor = args.offset + len(out['items'])
    if cursor < len(rows):
        out['next'] = cursor
    return out


def compact_write(root: Path, conn: sqlite3.Connection, result: dict,
                  requests: list[dict], args: argparse.Namespace) -> dict:
    rows = []
    for i, item in enumerate(result['items']):
        row: dict[str, Any] = {'input': i}
        if item.get('id'):
            row['ref'] = short_ref(conn, item['id'])
        if 'revision' in item:
            row['rev'] = item['revision']
        if item['ok']:
            row.update(action=item['action'], status=item['status'])
        else:
            error = item.get('error', '')
            match = re.match(r'^([A-Z_]+):', error)
            row['code'] = item.get('code') or (match[1] if match else 'ASSET_ERROR')
            if error:
                row['error'] = error
            if item.get('next'):
                row['next'] = item['next']
        rows.append(row)
    if len(rows) == 1:
        return {'ok': result['ok'], **{k: v for k, v in rows[0].items() if k != 'input'}}
    out = {'ok': result['ok']}
    for action in ('created', 'updated', 'unchanged'):
        count = sum(v.get('action') == action for v in rows)
        if count:
            out[action] = count
    if result['failed']:
        out['failed'] = result['failed']
    if args.details:
        out['items'] = rows
    else:
        errors = [v for v in rows if 'code' in v]
        if errors:
            out['errors'] = errors[:3]
    # Full IDs + input paths are stored outside model context. Returns are exact
    # historical outcomes, not sequential IDs tied to ephemeral session state.
    details = [{**v, 'path': requests[i]['path'], **({'id': result['items'][i]['id']} if result['items'][i].get('id') else {})}
               for i, v in enumerate(rows)]
    out['receipt'] = save_receipt(root, details, 'put')
    while len(wire(out).encode()) + 1 > args.budget and (out.get('items') or out.get('errors')):
        key = 'items' if out.get('items') else 'errors'
        out[key].pop()
        out['details_omitted'] = True
    return out


def execute(args: argparse.Namespace) -> dict:
    if not 384 <= args.budget <= 65536:
        db.fail('OUTPUT_BUDGET: choose 384..65536 UTF-8 bytes')
    root = Path(args.root).expanduser().resolve()
    catalog.guard(root)
    with db.project_lock(root):
        cfg = assetctl.config(root)
        if args.command in {'put', 'check'}:
            _receipt_dir(root)
        if args.command == 'receipt':
            return page_receipt(root, args)
        with contextlib.closing(db.connect(root)) as conn:
            catalog.ensure(root, conn, fresh=getattr(args, 'fresh', False) or args.command == 'check')
            if args.command in {'get', 'find'}:
                if args.hash_budget_mib < 0:
                    db.fail('HASH_BUDGET: use nonnegative MiB; 0 explicitly means unlimited')
                read_budget = [args.hash_budget_mib * 1024 * 1024 if args.hash_budget_mib else -1]
                if args.command == 'get':
                    card = catalog.load(root, identify(root, conn, args.ref))
                    if args.fields:
                        fields = args.fields.split(',')
                        if not fields or any(v not in db.INPUT | db.SYSTEM for v in fields):
                            db.fail('BAD_FIELDS: choose card fields such as source,rights,restrictions,files')
                        out = {'ok': True, 'metadata_only': True,
                               'ref': short_ref(conn, card['id']), 'rev': card['revision'],
                               'fields': {v: card.get(v) for v in fields}}
                    else:
                        out = {'ok': True, **brief(root, conn, card, args, read_budget)}
                else:
                    found = catalog.find(conn, args)
                    out = {'ok': True, 'items': []}
                    if args.summaries:
                        out['summaries_only'] = True
                    for row in found['items']:
                        if args.summaries:
                            value = {'ref': short_ref(conn, row['id']), 'rev': row['revision'],
                                     'path': row['path'], 'use': row['summary'], 'status': row['status']}
                        else:
                            value = brief(root, conn, catalog.load(root, row['id']), args, read_budget)
                        # Keep complete safety fields. Stop at a row boundary.
                        candidate = {**out, 'items': [*out['items'], value]}
                        if len(wire(candidate).encode()) + 40 > args.budget:
                            if out['items']:
                                break
                            value = {'ref': short_ref(conn, row['id']), 'usable': False,
                                     'blocked': [{'code': 'DETAIL_REQUIRED'}],
                                     'next': 'get ' + short_ref(conn, row['id']) + ' --budget 65536'}
                        out['items'].append(value)
                    cursor = args.offset + len(out['items'])
                    if cursor < found['total']:
                        out['next'] = cursor
                conn.commit()  # Persist hash evidence only, never a cached approval.
                return out
            if args.command == 'put':
                incoming = assetctl.requests(args)
                result = catalog.capture(root, conn, cfg, incoming, args.hash_budget_mib)
                conn.commit()
                return compact_write(root, conn, result, incoming, args)
            if args.command == 'check':
                result = catalog.gate(root, conn, args, cfg)
                if result['ok']:
                    return {'ok': True}
                out = {'ok': False, 'failed': result['error_count'], 'errors': result['errors'][:3]}
                out['receipt'] = save_receipt(root, result['errors'], 'check')
                if result['truncated']:
                    out['receipt_truncated'] = True
                while len(wire(out).encode()) + 1 > args.budget and out['errors']:
                    out['errors'].pop()
                return out
            db.fail('BAD_COMMAND')


def main() -> int:
    try:
        args = parser().parse_args()
        result = execute(args)
        data = wire(result)
        if len(data.encode('utf-8')) + 1 > args.budget:
            # No successful reuse claim may survive hidden constraints.
            result = {'ok': False, 'code': 'OUTPUT_BUDGET',
                      'next': 'increase --budget or use get --fields for selected metadata'}
            if args.command == 'put':
                # Mutation may already have committed: never encourage blind retry.
                result['next'] = 'write may have committed; get the input path before retrying'
        print(wire(result))
        return 0 if result['ok'] else 1
    except (db.AssetError, OSError, ValueError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        message = str(exc)
        match = re.match(r'^([A-Z_]+):', message)
        code = match[1] if match else ('INDEX_ERROR' if isinstance(exc, sqlite3.Error) else 'ASSET_ERROR')
        result = {'ok': False, 'code': code, 'error': message[:200]}
        cap = getattr(locals().get('args'), 'budget', 384)
        cap = max(384, min(cap, 65536))
        while len(wire(result).encode('utf-8')) + 1 > cap and result['error']:
            result['error'] = result['error'][:-1]
        print(wire(result))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
