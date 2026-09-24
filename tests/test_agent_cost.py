"""Token-oriented interface contracts. No model or tokenizer in runtime tests."""
import concurrent.futures
import contextlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/assetkit/scripts'
sys.path.insert(0, str(SCRIPTS))
import agent
import catalog
import ledger
import verification


class AgentCostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='assetkit context ')
        self.root = Path(self.tmp.name).resolve()
        self.run_script('bootstrap.py', '--project', str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, name, *args, ok=True, stdin=None):
        script = SCRIPTS / name if name != 'ak.py' else self.root / '.assets/ak.py'
        cmd = [sys.executable, '-B', '-S', str(script)]
        if name in {'agent.py', 'assetctl.py'}:
            cmd += ['--root', str(self.root)]
        proc = subprocess.run(cmd + list(args), cwd=self.root, input=stdin, text=True,
                              encoding='utf-8', capture_output=True, env={**os.environ, 'PYTHONUTF8': '1'})
        data = json.loads(proc.stdout or proc.stderr)
        self.assertEqual(proc.returncode == 0, ok, proc.stdout + proc.stderr)
        self.last_bytes = len(proc.stdout.encode())
        return data

    def call(self, *args, **kwargs):
        return self.run_script('ak.py', *args, **kwargs)

    def file(self, path, text='fixture'):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return p

    def put(self, path='docs/hero.md', **kwargs):
        if not (self.root / path).exists():
            self.file(path)
        return self.call('put', path, '--use', '首页 hero 主视觉说明', **kwargs)

    def card(self, ref):
        metadata = self.call('get', ref, '--fields', 'id')['fields']
        path = self.root / '.assets/records' / (metadata['id'] + '.json')
        return path, json.loads(path.read_text(encoding='utf-8'))

    def ready(self, ref, restrictions=None, relations=None):
        p, card = self.card(ref)
        changes = {'status': 'ready', 'source': {'kind': 'authored', 'ref': 'test-fixture'},
                   'rights': {'status': 'restricted', 'license': 'internal-test'},
                   'reviewed_by': 'test', 'review_evidence': 'synthetic fixture only'}
        if restrictions is not None: changes['restrictions'] = restrictions
        if relations is not None: changes['relations'] = relations
        self.run_script('assetctl.py', 'patch', card['id'], '--expect-revision', str(card['revision']),
                        '--patch', json.dumps(changes, ensure_ascii=False))
        return card['id']

    def test_short_launcher_and_idempotent_bootstrap(self):
        first = (self.root / '.assets/ak.py').read_bytes()
        result = self.run_script('bootstrap.py', '--project', str(self.root))
        self.assertEqual(result['entry_files'], [])
        self.assertEqual(first, (self.root / '.assets/ak.py').read_bytes())
        self.put()
        self.assertEqual(self.call('get', 'docs/hero.md')['path'], 'docs/hero.md')

    def test_modified_launcher_not_overwritten(self):
        p = self.root / '.assets/ak.py'
        p.write_text('user code', encoding='utf-8')
        self.run_script('bootstrap.py', '--project', str(self.root), ok=False)
        self.assertEqual(p.read_text(), 'user code')

    def test_find_combines_checks_and_preserves_constraints(self):
        item = self.put()
        self.ready(item['ref'], ['禁止用于外部广告'])
        result = self.call('find', 'hero')['items'][0]
        self.assertTrue(result['usable'])
        self.assertEqual(result['restrictions'], ['禁止用于外部广告'])
        self.assertLess(self.last_bytes, 2049)
        self.assertNotIn('index', result)

    def test_no_cached_approval_after_content_change(self):
        item = self.put(); self.ready(item['ref'])
        self.assertTrue(self.call('get', item['ref'])['usable'])
        self.file('docs/hero.md', 'mutated bytes')
        result = self.call('find', 'hero')['items'][0]
        self.assertFalse(result['usable'])
        self.assertIn('STALE_CONTENT', str(result))

    def test_known_path_get_and_metadata_projection(self):
        self.put()
        result = self.call('get', 'docs/hero.md', '--fields', 'source,rights')
        self.assertTrue(result['metadata_only'])
        self.assertEqual(set(result['fields']), {'source', 'rights'})
        self.assertNotIn('usable', result)

    def test_oversized_safety_fields_fail_closed(self):
        item = self.put()
        self.ready(item['ref'], ['禁止场景' * 40] * 5)
        result = self.call('find', 'hero', '--budget', '384')
        self.assertFalse(result['items'][0]['usable'])
        self.assertIn('DETAIL_REQUIRED', str(result))
        self.assertLessEqual(self.last_bytes, 384)
        self.call('get', item['ref'], '--budget', '384', ok=False)
        result = self.call('get', item['ref'], '--budget', '65536')
        self.assertTrue(result['usable'])
        self.assertEqual(len(result['restrictions']), 5)

    def test_pagination_never_loops_or_loses_rows(self):
        for i in range(5): self.put(f'docs/hero{i}.md')
        offset = 0; seen = set()
        while True:
            page = self.call('find', 'hero', '--budget', '512', '--offset', str(offset))
            self.assertLessEqual(self.last_bytes, 512)
            for row in page['items']:
                self.assertNotIn(row['ref'], seen); seen.add(row['ref'])
            if 'next' not in page: break
            self.assertGreater(page['next'], offset)
            offset = page['next']
        self.assertEqual(len(seen), 5)

    def test_summaries_open_no_cards_on_warm_index(self):
        self.put()
        self.call('find', 'hero', '--summaries')
        args = agent.parser().parse_args(['--root', str(self.root), 'find', 'hero', '--summaries'])
        with patch.object(catalog, 'load', side_effect=AssertionError('unexpected card read')):
            result = agent.execute(args)
        self.assertTrue(result['summaries_only'])
        self.assertNotIn('usable', result['items'][0])

    def test_prefix_collision_fails_closed_and_reindex_keeps_ref(self):
        self.put()
        with contextlib.closing(ledger.connect(self.root)) as conn:
            conn.execute('CREATE TEMP TABLE collision_fixture(id TEXT)')
            original = catalog.load(self.root, conn.execute('SELECT id FROM cards').fetchone()[0])
            one = 'ast_12345678' + '1' * 24
            two = 'ast_12345678' + '2' * 24
            for asset_id in (one, two):
                card = {**original, 'id': asset_id}
                path = self.root / '.assets/records' / (asset_id + '.json')
                ledger.atomic_json(path, card)
                ledger.index_card(conn, path, card)
            conn.commit()
            self.assertGreater(len(agent.short_ref(conn, one)), 9)
            with self.assertRaises(ledger.AssetError):
                agent.identify(self.root, conn, '@12345678')
        ref = self.call('find', 'hero')['items'][0]['ref']
        self.run_script('assetctl.py', 'reindex')
        self.assertEqual(self.call('get', ref)['ref'], ref)

    def test_touch_preserves_card_revision_and_review(self):
        item = self.put(); self.ready(item['ref'])
        path, card = self.card(item['ref']); before = path.read_bytes()
        f = self.root / 'docs/hero.md'; os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 10000000))
        # No revision required to prove this is a no-op, and no approval churn.
        result = self.call('put', 'docs/hero.md')
        self.assertEqual(result['action'], 'unchanged')
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(path.read_bytes(), before)
        with contextlib.closing(ledger.connect(self.root)) as conn:
            with patch.object(ledger, 'inspect_file', side_effect=AssertionError('unexpected hash')):
                result = catalog.capture_one(self.root, conn, {}, {'path': 'docs/hero.md'}, [0])
                self.assertEqual(result['bytes_hashed'], 0)

    def test_reuse_auto_hash_cache_and_forced_hash(self):
        item = self.put(); self.ready(item['ref'])
        _, card = self.card(item['ref'])
        f = self.root / 'docs/hero.md'; os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 10000000))
        with contextlib.closing(ledger.connect(self.root)) as conn:
            one = verification.evaluate(self.root, card, conn=conn); conn.commit()
            two = verification.evaluate(self.root, card, conn=conn)
            three = verification.evaluate(self.root, card, mode='hash', conn=conn)
            self.assertGreater(one['bytes_hashed'], 0)
            self.assertEqual(two['bytes_hashed'], 0)
            self.assertGreater(three['bytes_hashed'], 0)

    def test_snapshot_touch_is_noop_but_bytes_are_immutable(self):
        self.file('release.md')
        item = self.call('put', 'release.md', '--snapshot')
        f = self.root / 'release.md'; os.utime(f, ns=(0, f.stat().st_mtime_ns + 10000000))
        self.assertEqual(self.call('put', 'release.md')['action'], 'unchanged')
        self.file('release.md', 'changed')
        self.assertIn('IMMUTABLE_SNAPSHOT', str(self.call('put', 'release.md', '--expect-revision', '1', ok=False)))

    def test_missing_dependency_and_dependency_restrictions(self):
        dep = self.put('docs/dep.md'); dep_id = self.ready(dep['ref'], ['内部使用，不可再分发'])
        main = self.put(); main_id = self.ready(main['ref'], relations=[{'type': 'depends_on', 'id': dep_id}])
        ok = self.call('get', main['ref'])
        self.assertTrue(ok['usable']); self.assertIn('不可再分发', str(ok))
        (self.root / 'docs/dep.md').unlink()
        result = self.call('get', main['ref'])
        self.assertFalse(result['usable']); self.assertIn('MISSING_FILE', str(result))
        legacy = self.run_script('assetctl.py', 'resolve', main_id, '--intent', 'reuse', '--verify', 'hash', ok=False)
        self.assertFalse(legacy['usable'])

    def test_cycle_limit_and_revoked_dependency(self):
        a = self.put('docs/a.md'); b = self.put('docs/b.md')
        aid = self.ready(a['ref']); bid = self.ready(b['ref'], relations=[{'type':'depends_on','id':aid}])
        self.ready(a['ref'], relations=[{'type':'depends_on','id':bid}])
        result = self.call('get', a['ref'])
        self.assertIn('DEPENDENCY_CYCLE', str(result)); self.assertFalse(result['usable'])
        _, card = self.card(a['ref'])
        limited = verification.evaluate(self.root, card, max_nodes=1)
        self.assertIn('DEPENDENCY_LIMIT', str(limited['issues']))
        self.assertFalse(limited['usable'])

    def test_hash_budget_blocks_without_false_usable(self):
        item = self.put(); self.ready(item['ref'])
        _, card = self.card(item['ref'])
        value = verification.evaluate(self.root, card, mode='hash', budget=[0])
        self.assertFalse(value['usable']); self.assertIn('HASH_BUDGET', str(value['issues']))

    def test_batch_stdin_compact_receipts_and_partial_failure(self):
        for i in range(20): self.file(f'docs/note{i}.md', str(i))
        lines = '\n'.join(json.dumps({'path':f'docs/note{i}.md','use':'batch'},ensure_ascii=False) for i in range(20))
        first = self.call('put', '--batch', '-', stdin=lines)
        self.assertEqual(first['created'], 20); self.assertLess(self.last_bytes, 200)
        again = self.call('put', '--batch', '-', stdin=lines)
        self.assertEqual(again['unchanged'], 20); self.assertLess(self.last_bytes, 200)
        receipt = self.call('receipt', first['receipt'], '--limit', '2')
        self.assertTrue(receipt['historical']); self.assertEqual(len(receipt['items']),2)
        self.assertEqual(receipt['next'], 2)
        partial = self.call('put', '--batch', '-', stdin=lines + '\n{"path":"missing.md"}', ok=False)
        self.assertEqual(partial['failed'], 1); self.assertEqual(partial['errors'][0]['input'],20)
        full = self.call('receipt', partial['receipt'], '--offset','20')
        self.assertEqual(full['items'][0]['code'],'MISSING_ASSET')

    def test_bad_batch_and_invalid_budget_have_no_writes(self):
        self.file('a.md')
        self.call('put','--batch','-',stdin='{"path":"a.md","execute":"bad"}',ok=False)
        self.call('put','a.md','--budget','1',ok=False)
        self.assertEqual(list((self.root/'.assets/records').glob('*.json')),[])

    def test_unknown_flags_and_unicode_errors_are_bounded(self):
        self.call('find','hero','--invented','x',ok=False)
        self.assertLessEqual(self.last_bytes,384)
        self.call('get','错'*200+'.md','--budget','384',ok=False)
        self.assertLessEqual(self.last_bytes,384)

    def test_receipt_tamper_is_detected(self):
        self.file('a.md'); self.file('b.md')
        receipt=self.call('put','a.md','b.md')['receipt']
        p=next((self.root/'.assets/cache/receipts').glob(receipt+'*.json'))
        p.write_text('{"items":[]}',encoding='utf-8')
        self.assertIn('CORRUPT_RECEIPT',str(self.call('receipt',receipt,ok=False)))

    def test_ref_is_retrievable_after_context_reset(self):
        item=self.put(); self.ready(item['ref'])
        a=self.call('get',item['ref'])
        b=self.call('get',item['ref'])
        self.assertEqual(a,b)  # No "already sent" suppression or hidden session state.


if __name__ == '__main__':
    unittest.main()
