#!/usr/bin/env python3
"""AssetKit 0.2.0：本地资产账本；Python 3.10+，仅使用标准库。

卡片是元数据事实源；SQLite 只是可重建的检索缓存。
不移动/删除资产，不连接网络，不执行资产中的内容，不提供权限认证。
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator

MAX_JSON = 65536
KINDS = {"document", "image", "video", "audio", "model-3d", "model-ml", "dataset", "design", "template", "other"}
STATES = {"candidate", "ready", "deprecated", "archived"}
ROLES = {"primary", "source", "preview", "transcript", "config", "dependency", "readme"}
RELATIONS = {"derived_from", "supersedes", "depends_on"}
EDITABLE = {"title", "summary", "use_when", "restrictions", "tags", "aliases", "status", "rights", "source", "relations", "reviewed_by", "review_evidence"}
INPUT = EDITABLE | {"type", "domain", "logical_key", "content_version", "files", "storage_policy", "content_mode"}
SYSTEM = {"schema_version", "id", "revision", "created_at", "updated_at", "request_key", "request_fingerprint"}

class AssetError(Exception):
    pass

def fail(message: str) -> None:
    raise AssetError(message)

def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def encoded(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")

def read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_JSON:
        fail(f"JSON 超过 {MAX_JSON} 字节；请把正文和大型清单移到独立文件：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail("JSON 顶层必须为对象")
    return data

def atomic_json(path: Path, data: dict[str, Any]) -> None:
    payload = encoded(data)
    if len(payload) > MAX_JSON:
        fail("资产卡片超过 64 KiB；请拆分资产或把长内容移出卡片")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".asset-tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

@contextlib.contextmanager
def project_lock(root: Path) -> Iterator[None]:
    directory = root / ".assets"
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / ".lock").open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    acquired = False
    deadline = time.monotonic() + 10
    try:
        while not acquired:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    fail("资产账本正被另一进程占用；本次操作未取得锁")
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

def local_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        fail("文件路径必须是非空的 POSIX 风格仓库相对路径")
    p = PurePosixPath(value)
    if not p.parts or p.is_absolute() or ".." in p.parts or ":" in value or str(p) != value:
        fail(f"不允许绝对路径、上级目录或非规范路径：{value}")
    path = root.joinpath(*p.parts)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        fail(f"路径或符号链接逃逸项目根目录：{value}")
    if p.parts[0] in {".assets", ".git", ".work"}:
        fail(f"不能将元数据、Git 内部文件或临时文件登记为正式资产：{value}")
    return path

def inspect_file(root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(entry, dict) or set(entry) - {"path", "role"}:
        fail("新增 files 条目仅接受 path、role；校验和等字段由工具生成")
    path = local_path(root, entry.get("path", ""))
    role = entry.get("role", "primary")
    if role not in ROLES or not path.is_file():
        fail(f"文件不存在，或 role 不合法：{entry}")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        fail(f"计算校验和时文件发生变更：{entry['path']}")
    return {"path": entry["path"], "role": role, "sha256": digest.hexdigest(), "bytes": after.st_size,
            "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream"}

def text(value: Any, field: str, maximum: int, required: bool = True) -> None:
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        fail(f"{field} 必须为{'非空' if required else ''}字符串，最多 {maximum} 个字符")

def text_list(value: Any, field: str, count: int, length: int, minimum: int = 0) -> None:
    if not isinstance(value, list) or not minimum <= len(value) <= count:
        fail(f"{field} 必须为列表，条目数 {minimum}～{count}")
    for item in value:
        text(item, field, length)

def valid_card(root: Path, card: dict[str, Any]) -> None:
    unknown = set(card) - INPUT - SYSTEM
    if unknown:
        fail(f"未知字段：{sorted(unknown)}")
    if card.get("schema_version") != 1:
        fail("不支持的 schema_version")
    if not re.fullmatch(r"ast_[0-9a-f]{32}", card.get("id", "")):
        fail("资产 id 格式不合法")
    if type(card.get("revision")) is not int or card["revision"] < 1:
        fail("revision 必须是正整数")
    if card.get("type") not in KINDS or card.get("status") not in STATES:
        fail("资产 type 或 status 不合法")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", card.get("domain", "")):
        fail("domain 必须是 kebab-case")
    text(card.get("logical_key"), "logical_key", 160)
    if not re.fullmatch(r"[a-z0-9]+(?:[-/][a-z0-9]+)*", card["logical_key"]):
        fail("logical_key 仅允许小写字母、数字、单个连字符或斜线")
    mode = card.get("content_mode", "snapshot")
    if mode not in {"snapshot", "live"}:
        fail("content_mode 必须为 snapshot 或 live")
    if type(card.get("content_version")) is not int or (mode == "snapshot" and card["content_version"] < 1) or (mode == "live" and card["content_version"] != 0):
        fail("snapshot 的 content_version 必须为正整数；live 固定为 0")
    for field, length in (("title", 100), ("summary", 240)):
        text(card.get(field), field, length)
    text_list(card.get("use_when"), "use_when", 3, 120, 1)
    for field, count, length in (("tags", 20, 48), ("aliases", 20, 80), ("restrictions", 5, 160)):
        text_list(card.get(field, []), field, count, length)
    for field in ("created_at", "updated_at", "request_key", "request_fingerprint"):
        text(card.get(field), field, 160)
    if card.get("storage_policy") not in {"managed", "in-place"}:
        fail("storage_policy 必须为 managed 或 in-place")
    source = card.get("source")
    if not isinstance(source, dict) or source.get("kind") not in {"authored", "generated", "uploaded", "imported", "unknown"}:
        fail("source.kind 不合法")
    text(source.get("ref", "unknown"), "source.ref", 1000)
    rights = card.get("rights")
    if not isinstance(rights, dict) or rights.get("status") not in {"unknown", "cleared", "restricted"}:
        fail("rights.status 不合法")
    text(rights.get("license", "unknown"), "rights.license", 160)
    text(rights.get("note", ""), "rights.note", 1000, False)
    if card["status"] == "ready":
        if rights["status"] == "unknown" or source["kind"] == "unknown":
            fail("来源或复用权限未知的资产不能设为 ready")
        for field in ("reviewed_by", "review_evidence"):
            text(card.get(field), field, 1000)
    files = card.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 512:
        fail("files 必须包含 1～512 个文件；大型集合请登记清单与入口，不逐文件展开")
    paths = set()
    for entry in files:
        if not isinstance(entry, dict):
            fail("files 条目必须为对象")
        local_path(root, entry.get("path", ""))
        if entry.get("role") not in ROLES or not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", "")):
            fail("files.role 或 sha256 不合法")
        if type(entry.get("bytes")) is not int or entry["bytes"] < 0:
            fail("files.bytes 不合法")
        if entry["path"] in paths:
            fail("同一卡片不能重复登记同一路径")
        paths.add(entry["path"])
    if sum(f["role"] == "primary" for f in files) != 1:
        fail("每张资产卡片必须且只能有一个 primary 入口文件")
    if card["storage_policy"] == "managed":
        slug = card["logical_key"].split("/")[-1]
        version = "working" if mode == "live" else f"v{card['content_version']:03d}"
        prefix = f"assets/{card['type']}/{card['domain']}/{slug}/{version}/"
        for entry in files:
            if not entry["path"].startswith(prefix):
                fail(f"受管资产必须存放在 {prefix}；存量原位登记请使用 storage_policy=in-place")
        primary_name = PurePosixPath(next(f["path"] for f in files if f["role"] == "primary")).name
        pattern = re.escape(slug) + r"--[a-z0-9]+(?:-[a-z0-9]+)*--" + re.escape(version) + r"\.[a-z0-9]+(?:\.[a-z0-9]+)*"
        if not re.fullmatch(pattern, primary_name):
            fail(f"主文件应命名为 {slug}--<variant>--{version}.<ext>")
    relations = card.get("relations", [])
    if not isinstance(relations, list) or len(relations) > 100:
        fail("relations 必须为最多 100 项的列表")
    for relation in relations:
        if not isinstance(relation, dict) or relation.get("type") not in RELATIONS or not re.fullmatch(r"ast_[0-9a-f]{32}", relation.get("id", "")):
            fail("关系类型或目标 id 不合法")
        if relation["id"] == card["id"]:
            fail("资产不能关联自身")

DDL = """
CREATE TABLE IF NOT EXISTS cards (
 id TEXT PRIMARY KEY, logical_key TEXT NOT NULL, content_version INTEGER NOT NULL,
 type TEXT NOT NULL, domain TEXT NOT NULL, status TEXT NOT NULL,
 title TEXT NOT NULL, summary TEXT NOT NULL, revision INTEGER NOT NULL,
 primary_path TEXT NOT NULL, body TEXT NOT NULL, search_text TEXT NOT NULL,
 mtime_ns INTEGER NOT NULL, ctime_ns INTEGER NOT NULL, file_size INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS by_filter ON cards(status,type,domain);
CREATE INDEX IF NOT EXISTS by_logical_key ON cards(logical_key,content_version);
"""

def connect(root: Path) -> sqlite3.Connection:
    directory = root / ".assets/cache"
    directory.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(directory / "catalog.sqlite", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    return conn

def index_card(conn: sqlite3.Connection, path: Path, card: dict[str, Any]) -> None:
    stat = path.stat()
    searchable = [card["id"], card["logical_key"], card["title"], card["summary"], *card["use_when"], *card.get("tags", []), *card.get("aliases", [])]
    primary = next(f["path"] for f in card["files"] if f["role"] == "primary")
    conn.execute("""INSERT OR REPLACE INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (card["id"], card["logical_key"], card["content_version"], card["type"], card["domain"], card["status"],
                  card["title"], card["summary"], card["revision"], primary, json.dumps(card, ensure_ascii=False),
                  "\n".join(searchable).casefold(), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))

def sync_index(root: Path, conn: sqlite3.Connection, force: bool = False) -> dict[str, int]:
    # 仅在程序内检查卡片 stat；只读取新增/变化卡片，不把账本展开给 LLM。
    cached = {r["id"]: (r["mtime_ns"], r["ctime_ns"], r["file_size"]) for r in conn.execute("SELECT id,mtime_ns,ctime_ns,file_size FROM cards")}
    present = set()
    changed = 0
    with conn:
        for path in sorted((root / ".assets/records").glob("*.json")):
            present.add(path.stem)
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
            if force or cached.get(path.stem) != signature:
                card = read_json(path)
                valid_card(root, card)
                if card["id"] != path.stem:
                    fail(f"卡片 id 与文件名不一致：{path.name}")
                index_card(conn, path, card)
                changed += 1
        missing = set(cached) - present
        conn.executemany("DELETE FROM cards WHERE id=?", [(i,) for i in missing])
    return {"updated": changed, "removed": len(missing)}

def card_path(root: Path, asset_id: str) -> Path:
    if not re.fullmatch(r"ast_[0-9a-f]{32}", asset_id):
        fail("id 必须使用工具返回的完整资产 id")
    return root / ".assets/records" / f"{asset_id}.json"

def write_card(root: Path, conn: sqlite3.Connection, card: dict[str, Any]) -> None:
    valid_card(root, card)
    # 文件和 SQLite 不是跨系统原子事务。先发布事实源，再更新缓存；下次 sync 可修复缓存。
    path = card_path(root, card["id"])
    atomic_json(path, card)
    with conn:
        index_card(conn, path, card)

def result_card(card: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"ok": True, "id": card["id"], "revision": card["revision"], "status": card["status"],
            "logical_key": card["logical_key"], "content_version": card["content_version"], **extra}

def add(root: Path, conn: sqlite3.Connection, args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    incoming = read_json(Path(args.manifest))
    if set(incoming) - INPUT:
        fail(f"新增请求含未知或系统管理字段：{sorted(set(incoming) - INPUT)}")
    text(args.request_key, "request_key", 160)
    card = dict(incoming)
    card.setdefault("status", "candidate")
    card.setdefault("content_mode", "snapshot")
    card.setdefault("content_version", 0 if card["content_mode"] == "live" else 1)
    card.setdefault("storage_policy", "managed")
    card.setdefault("rights", {"status": "unknown", "license": "unknown", "note": "仅供内部审阅，尚未确认复用权限"})
    card.setdefault("source", {"kind": "unknown", "ref": "unknown"})
    if not isinstance(card.get("files"), list):
        fail("新增请求必须包含 files 列表")
    card["files"] = [inspect_file(root, e) for e in card["files"]]
    fingerprint = hashlib.sha256(encoded(card)).hexdigest()
    asset_id = "ast_" + uuid.uuid5(uuid.UUID(config["project_id"]), args.request_key).hex
    path = card_path(root, asset_id)
    if path.exists():
        old = read_json(path)
        if old["request_fingerprint"] != fingerprint:
            fail("同一个 request-key 对应的内容发生变化；请使用新的操作键")
        return result_card(old, idempotent=True)
    moment = stamp()
    card.update(schema_version=1, id=asset_id, revision=1, created_at=moment, updated_at=moment,
                request_key=args.request_key, request_fingerprint=fingerprint)
    valid_card(root, card)
    if conn.execute("SELECT id FROM cards WHERE logical_key=? AND content_version=?", (card["logical_key"], card["content_version"])).fetchone():
        fail("logical_key + content_version 已存在；复用已有资产或显式登记新的内容版本")
    for relation in card.get("relations", []):
        if not card_path(root, relation["id"]).exists():
            fail(f"关系目标不存在：{relation['id']}")
    write_card(root, conn, card)
    return result_card(card, idempotent=False, card_path=path.relative_to(root).as_posix())

def patch(root: Path, conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    card = read_json(card_path(root, args.id))
    if card["revision"] != args.expect_revision:
        fail(f"REVISION_CONFLICT：期望 {args.expect_revision}，实际 {card['revision']}；请只重读此卡片的相关字段")
    changes = read_json(Path(args.patch_file)) if args.patch_file else json.loads(args.patch)
    if not isinstance(changes, dict) or not changes or set(changes) - EDITABLE:
        fail("patch 必须为非空字段对象，且只能修改可编辑语义字段；不能改路径、内容版本或校验和")
    new = {**card, **changes, "revision": card["revision"] + 1, "updated_at": stamp()}
    valid_card(root, new)
    for relation in new.get("relations", []):
        if not card_path(root, relation["id"]).exists():
            fail(f"关系目标不存在：{relation['id']}")
    # 标为 ready 时校验原文件未变；这是结构/完整性检查，不是授权真实性认证。
    if new["status"] == "ready":
        for e in new["files"]:
            actual = inspect_file(root, {"path": e["path"], "role": e["role"]})
            if actual["sha256"] != e["sha256"]:
                fail(f"内容已变化，不允许将旧版本标为 ready：{e['path']}")
    write_card(root, conn, new)
    return result_card(new)

def refresh(root: Path, conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    card = read_json(card_path(root, args.id))
    if card.get("content_mode", "snapshot") != "live":
        fail("refresh 只允许更新 live 工作资产；snapshot 必须发布新版本")
    if card["revision"] != args.expect_revision:
        fail(f"REVISION_CONFLICT：期望 {args.expect_revision}，实际 {card['revision']}")
    card["files"] = [inspect_file(root, {"path": f["path"], "role": f["role"]}) for f in card["files"]]
    card.update(summary=args.summary, use_when=json.loads(args.use_when), status="candidate",
                revision=card["revision"] + 1, updated_at=stamp())
    card.pop("reviewed_by", None)
    card.pop("review_evidence", None)
    write_card(root, conn, card)
    return result_card(card, notice="工作内容已刷新；旧审批已失效，需重新审阅。已有预览/转录不保证同步更新。")

def search(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    text(args.query, "query", 200, False)
    if not 1 <= args.limit <= 20 or args.offset < 0:
        fail("limit 必须为 1～20；offset 不得为负")
    terms = args.query.casefold().split()
    if len(terms) > 12:
        fail("检索词最多 12 个；优先使用任务关键词，而不是整段任务描述")
    clauses, params = [], []
    for term in terms:
        clauses.append("instr(search_text, ?) > 0")
        params.append(term)
    for name in ("type", "domain", "status"):
        value = getattr(args, name)
        if value and value != "all":
            clauses.append(name + "=?")
            params.append(value)
    where = " AND ".join(clauses) or "1=1"
    total = conn.execute("SELECT COUNT(*) FROM cards WHERE " + where, params).fetchone()[0]
    rows = conn.execute("SELECT id,logical_key,content_version,title,summary,type,domain,status,revision,primary_path FROM cards WHERE " + where + " ORDER BY logical_key,content_version DESC,id LIMIT ? OFFSET ?", [*params, args.limit, args.offset]).fetchall()
    return {"ok": True, "items": [dict(r) for r in rows], "total": total,
            "next_offset": args.offset + args.limit if args.offset + args.limit < total else None,
            "notice": "这是候选摘要，不是复用许可；使用前 show 单条卡片检查限制、来源和文件。"}

def validate(root: Path, args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    errors, warnings, records = [], [], {}
    def issue(target: list, asset_id: str, message: str) -> None:
        target.append({"id": asset_id, "message": message})
    logical, registered = {}, set()
    for path in sorted((root / ".assets/records").glob("*.json")):
        try:
            card = read_json(path)
            valid_card(root, card)
            if card["id"] != path.stem:
                fail("卡片文件名与 id 不匹配")
            records[card["id"]] = card
            key = (card["logical_key"], card["content_version"])
            if key in logical:
                issue(errors, card["id"], f"重复逻辑资产版本：{key}；另一个 id={logical[key]}")
            logical[key] = card["id"]
            for entry in card["files"]:
                registered.add(entry["path"])
                actual_path = local_path(root, entry["path"])
                if not actual_path.is_file():
                    issue(errors if card["status"] in {"candidate", "ready"} else warnings, card["id"], f"文件不可用：{entry['path']}")
                elif args.hashes:
                    actual = inspect_file(root, {"path": entry["path"], "role": entry["role"]})
                    if actual["sha256"] != entry["sha256"]:
                        issue(errors, card["id"], f"文件校验和变化：{entry['path']}；snapshot 需新版本，live 需 refresh 并重审")
        except (AssetError, OSError, ValueError, KeyError, TypeError) as exc:
            issue(errors, path.stem, str(exc))
    for asset_id, card in records.items():
        for relation in card.get("relations", []):
            if relation["id"] not in records:
                issue(errors, asset_id, f"关系目标缺失：{relation['id']}")
    for folder in config.get("managed_roots", ["assets"]):
        base = local_path(root, folder)
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.name in {".gitkeep", ".DS_Store"}:
                continue
            relative = path.relative_to(root).as_posix()
            if relative not in registered:
                target = warnings if relative.startswith("assets/_inbox/") else errors
                issue(target, "unregistered", relative)
    limit = max(1, min(args.max_issues, 100))
    return {"ok": not errors, "checked": len(records), "error_count": len(errors), "warning_count": len(warnings),
            "errors": errors[:limit], "warnings": warnings[:limit], "truncated": len(errors) > limit or len(warnings) > limit,
            "scope": "仅验证卡片及 managed_roots；不检查语义正确性、真实授权、代码引用或模型兼容性。"}

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", action="version", version="AssetKit 0.2.0")
    p.add_argument("--root", default=".", help="项目根目录；默认当前目录")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="初始化项目级账本，不覆盖现有文件")
    a = commands.add_parser("add", help="新增一张卡片；文件须已在正式位置")
    a.add_argument("--manifest", required=True)
    a.add_argument("--request-key", required=True)
    s = commands.add_parser("search", help="分页检索短摘要；空格分词采用 AND 子串匹配")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("--type", choices=sorted(KINDS))
    s.add_argument("--domain")
    s.add_argument("--status", choices=["all", *sorted(STATES)], default="ready")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--offset", type=int, default=0)
    g = commands.add_parser("show", help="只读取指定卡片，不读取原始文件")
    g.add_argument("id")
    g.add_argument("--fields", default="", help="逗号分隔的顶层字段；不指定时返回完整卡片")
    u = commands.add_parser("patch", help="按 revision 乐观锁修改一张卡片的指定顶层字段")
    u.add_argument("id")
    u.add_argument("--expect-revision", type=int, required=True)
    patches = u.add_mutually_exclusive_group(required=True)
    patches.add_argument("--patch", help="JSON 顶层字段替换对象，不是 RFC 6902")
    patches.add_argument("--patch-file", help="UTF-8 JSON 补丁文件；避免 shell 引号问题")
    r = commands.add_parser("refresh", help="刷新 live 工作资产的指纹和摘要，自动撤销旧审批")
    r.add_argument("id")
    r.add_argument("--expect-revision", type=int, required=True)
    r.add_argument("--summary", required=True)
    r.add_argument("--use-when", required=True, help="JSON 字符串数组，说明更新后的复用场景")
    commands.add_parser("sync", help="增量同步索引，只解析变化的卡片")
    commands.add_parser("reindex", help="删除并完整重建派生索引，不改卡片或资产文件")
    v = commands.add_parser("validate", help="程序检查卡片、引用及受管资产；输出有数量上限")
    v.add_argument("--hashes", action="store_true", help="流式重算内容哈希，可能有较大磁盘 I/O")
    v.add_argument("--max-issues", type=int, default=20)
    return p

def execute(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    if not root.is_dir():
        fail("项目根目录不存在")
    # 拒绝明显的元数据符号链接重定向；仍只面向可信本地工作区，不提供竞态隔离。
    for relative in (".assets", ".assets/records", ".assets/cache", ".assets/.lock", ".assets/config.json"):
        if (root / relative).is_symlink():
            fail(f"元数据路径不能为符号链接：{relative}")
    with project_lock(root):
        config_path = root / ".assets/config.json"
        if args.command == "init":
            if not config_path.exists():
                atomic_json(config_path, {"schema_version": 1, "project_id": str(uuid.uuid4()), "managed_roots": ["assets"]})
            (root / ".assets/records").mkdir(parents=True, exist_ok=True)
            with contextlib.closing(connect(root)):
                pass
            return {"ok": True, "config": ".assets/config.json", "next": "读取 Skill 的 references/integration.md；用 install.py --bootstrap 合并项目入口，或手工合并 assets/project-entry.md。"}
        if not config_path.exists():
            fail("请先运行 init")
        config = read_json(config_path)
        if args.command == "show":
            card = read_json(card_path(root, args.id))
            valid_card(root, card)
            if args.fields:
                fields = [f.strip() for f in args.fields.split(",")]
                if set(fields) - INPUT - SYSTEM:
                    fail("fields 含未知字段")
                card = {f: card.get(f) for f in fields}
            return {"ok": True, "asset": card, "data_is_untrusted": True}
        if args.command == "validate":
            return validate(root, args, config)
        if args.command == "reindex":
            cache = root / ".assets/cache/catalog.sqlite"
            for suffix in ("", "-journal", "-wal", "-shm"):
                Path(str(cache) + suffix).unlink(missing_ok=True)
        with contextlib.closing(connect(root)) as conn:
            synchronized = sync_index(root, conn, force=args.command == "reindex")
            if args.command in {"sync", "reindex"}:
                return {"ok": True, **synchronized}
            if args.command == "add":
                return add(root, conn, args, config)
            if args.command == "patch":
                return patch(root, conn, args)
            if args.command == "refresh":
                return refresh(root, conn, args)
            if args.command == "search":
                return search(conn, args)
        fail("未知命令")

def main() -> int:
    try:
        result = execute(parser().parse_args())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    except (AssetError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
