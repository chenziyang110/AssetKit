"""隔离临时目录中的功能测试，不修改使用者项目。"""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "assetkit" / "scripts" / "assetctl.py"

class AssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.call("init")

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *args, ok=True):
        proc = subprocess.run([sys.executable, "-S", str(SCRIPT), "--root", str(self.root), *args], capture_output=True, text=True)
        data = json.loads(proc.stdout or proc.stderr)
        if ok:
            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
            self.assertTrue(data["ok"])
        else:
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(data["ok"])
        return data

    def request(self, slug="home-hero", version=1):
        v = f"v{version:03d}"
        path = self.root / f"assets/document/website/{slug}/{v}/{slug}--main--{v}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 示例\n首页复用资产，内容仅用于测试。", encoding="utf-8")
        payload = {"type": "document", "domain": "website", "logical_key": f"website/{slug}", "content_version": version,
                   "title": "首页产品说明", "summary": "用于首页的中文产品介绍与说明", "use_when": ["制作首页文案"],
                   "aliases": ["landing hero", "主视觉"], "tags": ["首页", "hero"],
                   "files": [{"path": path.relative_to(self.root).as_posix(), "role": "primary"}],
                   "source": {"kind": "authored", "ref": "tests"}}
        req = self.root / f"{slug}-{version}.json"
        req.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return req, path, payload

    def add(self, slug="home-hero", key="task-1.hero", version=1):
        req, path, payload = self.request(slug, version)
        result = self.call("add", "--manifest", str(req), "--request-key", key)
        return result, req, path, payload

    def test_add_search_and_small_show(self):
        item, _, _, _ = self.add()
        self.assertEqual(self.call("search", "首页")["total"], 0)
        search = self.call("search", "首页", "--status", "all")
        self.assertEqual(search["total"], 1)
        self.assertNotIn("files", search["items"][0])
        self.assertEqual(self.call("search", "landing", "--status", "all")["total"], 1)
        shown = self.call("show", item["id"], "--fields", "id,revision")
        self.assertEqual(set(shown["asset"]), {"id", "revision"})

    def test_idempotency_and_conflict(self):
        item, request, path, _ = self.add()
        same = self.call("add", "--manifest", str(request), "--request-key", "task-1.hero")
        self.assertEqual(item["id"], same["id"])
        self.assertTrue(same["idempotent"])
        path.write_text("changed", encoding="utf-8")
        self.call("add", "--manifest", str(request), "--request-key", "task-1.hero", ok=False)

    def test_revision_conflict_and_protected_fields(self):
        item, _, _, _ = self.add()
        self.call("patch", item["id"], "--expect-revision", "1", "--patch", '{"tags":["new"]}')
        self.call("patch", item["id"], "--expect-revision", "1", "--patch", '{"tags":["old"]}', ok=False)
        self.call("patch", item["id"], "--expect-revision", "2", "--patch", '{"files":[]}', ok=False)

    def test_ready_requires_review_and_rights(self):
        item, _, _, _ = self.add()
        self.call("patch", item["id"], "--expect-revision", "1", "--patch", '{"status":"ready"}', ok=False)
        update = {"status": "ready", "rights": {"status": "restricted", "license": "internal-test", "note": "测试用途"},
                  "reviewed_by": "test-runner", "review_evidence": "unit-test fixture; not a production approval"}
        self.call("patch", item["id"], "--expect-revision", "1", "--patch", json.dumps(update))
        self.assertEqual(self.call("search", "首页")["total"], 1)

    def test_reindex_and_incremental_sync(self):
        item, _, _, _ = self.add()
        self.assertEqual(self.call("sync")["updated"], 0)
        self.assertEqual(self.call("reindex")["updated"], 1)
        path = self.root / ".assets/records" / (item["id"] + ".json")
        data = json.loads(path.read_text())
        data["summary"] = "外部合并进来的新摘要"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.call("search", "新摘要", "--status", "all")["total"], 1)
        self.assertEqual(self.call("sync")["updated"], 0)

    def test_hash_change_and_unregistered_file(self):
        _, _, path, _ = self.add()
        self.assertTrue(self.call("validate", "--hashes")["ok"])
        path.write_text("changed")
        report = self.call("validate", "--hashes", ok=False)
        self.assertEqual(report["error_count"], 1)
        (self.root / "assets/loose.txt").write_text("orphan")
        self.assertEqual(self.call("validate", ok=False)["error_count"], 1)

    def test_paths_and_naming(self):
        request, _, payload = self.request()
        for unsafe in (".", "../outside.txt", "/etc/passwd", "assets/../secret.txt", "C:/secret.txt"):
            payload["files"][0]["path"] = unsafe
            request.write_text(json.dumps(payload), encoding="utf-8")
            self.call("add", "--manifest", str(request), "--request-key", "unsafe", ok=False)
        path = self.root / "bad.md"
        path.write_text("legacy")
        payload["files"][0]["path"] = "bad.md"
        request.write_text(json.dumps(payload), encoding="utf-8")
        self.call("add", "--manifest", str(request), "--request-key", "naming", ok=False)
        payload["storage_policy"] = "in-place"
        request.write_text(json.dumps(payload), encoding="utf-8")
        self.call("add", "--manifest", str(request), "--request-key", "legacy")

    def test_duplicate_logical_version_and_new_version(self):
        item, request, _, _ = self.add()
        self.call("add", "--manifest", str(request), "--request-key", "other-key", ok=False)
        newer, _, _, _ = self.add(key="task-2.hero", version=2)
        self.assertNotEqual(item["id"], newer["id"])
        self.assertEqual(item["logical_key"], newer["logical_key"])
        self.assertEqual(self.call("search", "首页", "--status", "all")["total"], 2)

    def test_parallel_add_is_idempotent(self):
        request, _, _ = self.request()
        def attempt(_):
            return self.call("add", "--manifest", str(request), "--request-key", "parallel-key")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        self.assertEqual(len({r["id"] for r in results}), 1)
        self.assertEqual(sum(not r["idempotent"] for r in results), 1)

    def test_live_refresh_invalidates_approval(self):
        path = self.root / "architecture.md"
        path.write_text("old")
        request = self.root / "live.json"
        payload = {"type": "document", "domain": "engineering", "logical_key": "engineering/architecture", "title": "架构文档",
                   "summary": "现有架构", "use_when": ["修改服务边界"], "content_mode": "live", "storage_policy": "in-place",
                   "files": [{"path": "architecture.md", "role": "primary"}]}
        request.write_text(json.dumps(payload))
        result = self.call("add", "--manifest", str(request), "--request-key", "live-doc")
        self.assertEqual(result["content_version"], 0)
        path.write_text("new architecture")
        self.call("validate", "--hashes", ok=False)
        self.call("refresh", result["id"], "--expect-revision", "1", "--summary", "更新后的服务架构", "--use-when", '["理解服务边界"]')
        self.assertTrue(self.call("validate", "--hashes")["ok"])
        shown = self.call("show", result["id"])["asset"]
        self.assertEqual(shown["status"], "candidate")
        self.assertEqual(shown["revision"], 2)
        self.assertNotIn("reviewed_by", shown)

    def test_relation_and_page_limit(self):
        request, _, payload = self.request()
        payload["relations"] = [{"type": "depends_on", "id": "ast_" + "0" * 32}]
        request.write_text(json.dumps(payload))
        self.call("add", "--manifest", str(request), "--request-key", "bad-relation", ok=False)
        self.call("search", "", "--limit", "100", ok=False)

if __name__ == "__main__":
    unittest.main()
