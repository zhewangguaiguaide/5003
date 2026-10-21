"""成员① JSONL 快照接收：结构验证、原字段落库、原子同步与索引失效标记。

不重新推断学年或执行成员②的薄页规则；语义缺陷必须由语料 owner 修正。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .corpus import canonicalize_url, normalize_text
from .db import DOCUMENT_COLS, init_schema

TEXT_FIELDS = ("url", "title", "source", "content", "date", "crawled_at", "topic", "column", "academic_year", "error")
LIST_FIELDS = ("image_urls", "file_urls")


def read_corpus(path):
    """验证完整快照后才允许数据库变更；不静默去重或重写字段。"""
    raw = Path(path).read_bytes()
    rows, urls, fingerprints = [], set(), set()
    for number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict) or set(row) != set(TEXT_FIELDS + LIST_FIELDS):
                raise ValueError("必须含契约规定的 12 个字段，不能缺少或额外增加字段")
            if any(not isinstance(row[key], str) for key in TEXT_FIELDS):
                raise ValueError("文本字段必须是字符串")
            if any(not isinstance(row[key], list) or any(not isinstance(v, str) for v in row[key]) for key in LIST_FIELDS):
                raise ValueError("附件/图片字段必须是字符串数组")
            parts = urlsplit(row["url"])
            if parts.scheme not in ("http", "https") or not parts.netloc:
                raise ValueError("URL 必须为绝对 HTTP(S) 地址")
            if row["url"] != canonicalize_url(row["url"]):
                raise ValueError("URL 尚未规范化，请由语料 owner 重新导出")
            if row["error"] or not row["content"].strip():
                raise ValueError("交付语料不能含失败或空正文")
            if row["url"] in urls:
                raise ValueError("重复 URL")
            fp = hashlib.sha256(normalize_text(row["content"]).encode("utf-8")).hexdigest()
            if fp in fingerprints:
                raise ValueError("重复规范化正文")
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"JSONL 第 {number} 行：{exc}") from exc
        urls.add(row["url"])
        fingerprints.add(fp)
        rows.append(row)
    if not rows:
        raise ValueError("拒绝空快照，防止误清空文档层")
    return rows, hashlib.sha256(raw).hexdigest()


def import_corpus(path, conn):
    rows, sha256 = read_corpus(path)
    init_schema(conn)
    report = dict(source="jsonl", source_path=str(Path(path).resolve()), sha256=sha256,
                  input=len(rows), inserted=0, updated=0, unchanged=0,
                  removed_unreferenced=0, retained_inactive=0,
                  semantic_review="pending_member2", release_ready=False)
    incoming = {row["url"] for row in rows}
    with conn:
        existing = {row[0]: row for row in conn.execute(
            "SELECT " + ",".join(DOCUMENT_COLS) + ",active FROM documents")}
        for row in rows:
            values = {key: row[key] for key in DOCUMENT_COLS if key not in ("image_urls", "file_urls", "column_name")}
            values.update(image_urls=json.dumps(row["image_urls"], ensure_ascii=False),
                          file_urls=json.dumps(row["file_urls"], ensure_ascii=False), column_name=row["column"])
            old = existing.get(row["url"])
            changed = old is None or tuple(values[key] for key in DOCUMENT_COLS) != old[:-1] or old[-1] != 1
            report["inserted" if old is None else "updated" if changed else "unchanged"] += 1
            values.update(corpus_sha256=sha256, dirty=int(changed))
            conn.execute(
                "INSERT INTO documents (" + ",".join(DOCUMENT_COLS) + ",corpus_sha256,active,index_dirty) VALUES ("
                + ",".join(":" + key for key in DOCUMENT_COLS) + ",:corpus_sha256,1,1) ON CONFLICT(url) DO UPDATE SET "
                + ",".join(key + "=excluded." + key for key in DOCUMENT_COLS if key != "url")
                + ",corpus_sha256=excluded.corpus_sha256,active=1,index_dirty=CASE WHEN :dirty=1 THEN 1 ELSE documents.index_dirty END", values)
        for url in existing.keys() - incoming:
            if conn.execute("SELECT 1 FROM chunks WHERE doc_id=? LIMIT 1", (url,)).fetchone():
                conn.execute("UPDATE documents SET active=0,index_dirty=1 WHERE url=?", (url,))
                report["retained_inactive"] += 1
            else:
                conn.execute("DELETE FROM documents WHERE url=?", (url,))
                report["removed_unreferenced"] += 1
        report["active_documents"] = conn.execute("SELECT COUNT(*) FROM documents WHERE active=1").fetchone()[0]
        report["total_documents"] = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        if report["active_documents"] != len(rows):
            raise ValueError("活动文档数与快照不一致，回滚接收")
        conn.execute("INSERT INTO corpus_imports (source_path,sha256,imported_at,input_count,active_count,report_json) VALUES (?,?,?,?,?,?)",
                     (report["source_path"], sha256, datetime.now(timezone.utc).isoformat(),
                      len(rows), report["active_documents"], json.dumps(report, ensure_ascii=False)))
    return report


def document_quality(conn, columns):
    """接收层完整性检查；不宣称通过学年/薄页的语义质检。"""
    init_schema(conn)
    current = conn.execute("SELECT sha256,source_path,report_json FROM corpus_imports ORDER BY import_id DESC LIMIT 1").fetchone()
    docs = {row[0]: row for row in conn.execute("SELECT url,column_name,LENGTH(content),academic_year,corpus_sha256 FROM documents WHERE active=1")}
    seeds = [dict(column=c.name, url=url, status="ok" if canonicalize_url(url) in docs else "missing") for c in columns for url in c.seeds]
    coverage = {c.name: sum(row[1] == c.name for row in docs.values()) for c in columns}
    foreign_errors = [list(row) for row in conn.execute("PRAGMA foreign_key_check")]
    integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
    version_mismatch = sum(row[4] != current[0] for row in docs.values()) if current else 0
    implausible_years = []
    for url, _, _, year, _ in docs.values():
        if year:
            try:
                begin, end = map(int, year.split("-"))
                if end != begin + 1:
                    implausible_years.append(dict(url=url, academic_year=year))
            except ValueError:
                implausible_years.append(dict(url=url, academic_year=year))
    return dict(source="documents.active=1", corpus_sha256=current[0] if current else "",
                source_path=current[1] if current else "", active_documents=len(docs),
                total_documents=conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                seed_success=sum(s["status"] == "ok" for s in seeds), seeds=seeds, coverage=coverage,
                index_dirty=conn.execute("SELECT COUNT(*) FROM documents WHERE active=1 AND index_dirty=1").fetchone()[0],
                inactive_chunk_refs=conn.execute("SELECT COUNT(*) FROM chunks c JOIN documents d ON c.doc_id=d.url WHERE d.active=0").fetchone()[0],
                version_mismatch=version_mismatch, integrity=integrity, foreign_key_errors=foreign_errors,
                semantic_review="pending_member2", release_ready=False, suspicious_years=implausible_years,
                note="结构与来源核查不替代 F1/F2 语义修复；年份相邻也不证明标签适用整页")
