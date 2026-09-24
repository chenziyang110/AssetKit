"""Bounded declared-dependency verification. No model calls or native execution.

Local hash evidence caches bytes, never approval decisions. Every lookup checks
current file signatures and every authorization check reloads relevant cards.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

import ledger as db
import catalog
import profiles

DDL = '''CREATE TABLE IF NOT EXISTS assetkit_verified(
 path TEXT NOT NULL, sha256 TEXT NOT NULL, signature TEXT NOT NULL,
 PRIMARY KEY(path,sha256));'''


def remember(conn: sqlite3.Connection | None, path: str, sha: str, sig: dict) -> None:
    if conn is not None:
        conn.execute(DDL)
        # Only current local evidence is useful; prevent unbounded historical rows.
        conn.execute('DELETE FROM assetkit_verified WHERE path=?', (path,))
        conn.execute('INSERT INTO assetkit_verified VALUES(?,?,?)',
                     (path, sha, json.dumps(sig, sort_keys=True)))


def cached(conn: sqlite3.Connection | None, path: str, sha: str, sig: dict) -> bool:
    if conn is None:
        return False
    conn.execute(DDL)
    row = conn.execute('SELECT signature FROM assetkit_verified WHERE path=? AND sha256=?',
                       (path, sha)).fetchone()
    return bool(row and row[0] == json.dumps(sig, sort_keys=True))


def check_file(root: Path, item: dict, mode: str, budget: list[int],
               conn: sqlite3.Connection | None) -> tuple[str | None, int]:
    """Return blocker code, bytes hashed. Explicit hash never uses stat evidence."""
    path = catalog.safe_file(root, item['path'])
    if not path.is_file():
        return 'MISSING_FILE', 0
    sig = catalog.signature(path)
    if mode != 'hash' and (item.get('stat') == sig or cached(conn, item['path'], item['sha256'], sig)):
        return None, 0
    if mode == 'stat':
        return 'HASH_REQUIRED', 0
    size = sig['size']
    if budget[0] >= 0 and size > budget[0]:
        return 'HASH_BUDGET', 0
    if budget[0] >= 0:
        budget[0] -= size
    actual = db.inspect_file(root, {'path': item['path'], 'role': item['role']})
    if sig != catalog.signature(path):
        return 'CONTENT_RACE', size
    remember(conn, item['path'], actual['sha256'], sig)
    return (None if actual['sha256'] == item['sha256'] else 'STALE_CONTENT'), size


def evaluate(root: Path, card: dict, mode: str = 'auto', budget: list[int] | None = None,
             conn: sqlite3.Connection | None = None, max_nodes: int = 32,
             max_depth: int = 8) -> dict[str, Any]:
    """A bounded dependency closure, not an engine graph or a legal approval."""
    if mode not in {'stat', 'auto', 'hash'}:
        db.fail('INVALID_VERIFY: use stat, auto or hash')
    budget = budget if budget is not None else [64 * 1024 * 1024]
    seen: set[str] = set()
    active: set[str] = set()
    memo: dict[str, dict] = {card['id']: card}
    nodes: list[dict] = []
    issues: list[dict] = []
    issue_count = 0
    hashed = 0
    hashed_files = 0
    file_count = 0
    native: dict = {}
    complete = True

    def issue(code: str, asset_id: str, path: str | None = None) -> None:
        nonlocal issue_count
        issue_count += 1
        if len(issues) < 20:
            value = {'code': code, 'id': asset_id}
            if path is not None:
                value['path'] = path
            issues.append(value)

    def walk(asset_id: str, depth: int) -> None:
        nonlocal hashed, hashed_files, file_count, native, complete
        if asset_id in active:
            issue('DEPENDENCY_CYCLE', asset_id)
            complete = False
            return
        if asset_id in seen:
            return
        if len(seen) >= max_nodes or depth > max_depth:
            issue('DEPENDENCY_LIMIT', asset_id)
            complete = False
            return
        seen.add(asset_id)
        try:
            node = memo.get(asset_id) or catalog.load(root, asset_id)
            memo[asset_id] = node
        except (db.AssetError, OSError, ValueError, KeyError, TypeError):
            issue('DEPENDENCY_UNAVAILABLE', asset_id)
            complete = False
            return
        active.add(asset_id)
        nodes.append(node)
        if node['status'] != 'ready':
            issue('NOT_READY', asset_id)
        if node['rights']['status'] == 'unknown':
            issue('RIGHTS_UNKNOWN', asset_id)
        if node['source']['kind'] == 'unknown':
            issue('SOURCE_UNKNOWN', asset_id)
        primary = next(v['path'] for v in node['files'] if v['role'] == 'primary')
        primary_ok = False
        for item in node['files']:
            file_count += 1
            if file_count > 2048:
                issue('FILE_LIMIT', asset_id)
                complete = False
                break
            try:
                problem, read_bytes = check_file(root, item, mode, budget, conn)
            except (db.AssetError, OSError, ValueError):
                problem, read_bytes = 'UNSAFE_OR_UNREADABLE_FILE', 0
            hashed += read_bytes
            hashed_files += int(read_bytes > 0)
            if problem:
                issue(problem, asset_id, item['path'])
            elif item['role'] == 'primary':
                primary_ok = True
        if primary_ok:
            try:
                hint = profiles.hints(root, primary, node.get('source', {}).get('project', {}).get('profile'))
                if asset_id == card['id']:
                    native = hint
                if hint.get('import_required'):
                    issue('IMPORT_REQUIRED', asset_id, primary)
                if hint.get('unmaterialized'):
                    issue('PAYLOAD_UNMATERIALIZED', asset_id, primary)
            except (db.AssetError, OSError, ValueError, KeyError, TypeError):
                issue('NATIVE_HINT_ERROR', asset_id, primary)
        for rel in node.get('relations', []):
            if rel['type'] == 'depends_on':
                walk(rel['id'], depth + 1)
        active.remove(asset_id)

    walk(card['id'], 0)
    return {'usable': issue_count == 0 and complete, 'issues': issues,
            'issue_count': issue_count, 'complete': complete,
            'nodes': nodes, 'native': native,
            'bytes_hashed': hashed, 'hashed_files': hashed_files,
            'checked_files': min(file_count, 2048)}
