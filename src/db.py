"""规范化存储层（分工方案 §5.3，成员①交付）。

records 表是采集原始层（src/storage.py），本模块在其上提供：
- init_schema()            : 建 documents / chunks / crawl_runs / qa_logs 四表 + 索引
- migrate_from_records()   : records -> documents 迁移（URL 规范化 + 去重 + academic_year 下沉）
- log_crawl_run()          : 抓取审计（失败计数落库，接管交接单 R1 的正式方案）
- log_qa()                 : 问答留痕

设计约定（验收报告 §6.3 T4）：image/file_urls 维持 JSON 文本列，不拆 3NF；
向量索引由 WS-B 决定走 sqlite-vec 还是 FAISS 侧车，本层不预设。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from .corpus import canonicalize_url, deduplicate, infer_academic_year
from .storage import Record
from .parser import clean_title

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"

DOCUMENT_COLS = ("url", "title", "source", "topic", "academic_year",
                 "date", "crawled_at", "content", "image_urls", "file_urls", "column_name")


def init_schema(conn: sqlite3.Connection) -> None:
    """按 schema.sql 建表建索引；幂等（CREATE IF NOT EXISTS）。"""
    conn.execute("PRAGMA foreign_keys=ON")
    # CREATE IF NOT EXISTS 不会给旧表补字段：先做可重复的升级，再建新索引。
    columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    if columns:
        additions = {
            "column_name": "TEXT NOT NULL DEFAULT ''",
            "active": "INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))",
            "index_dirty": "INTEGER NOT NULL DEFAULT 1 CHECK (index_dirty IN (0, 1))",
            "corpus_sha256": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {definition}")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def migrate_from_records(records: Iterable[Record], conn: sqlite3.Connection) -> dict:
    """原始 records 迁移。已有 JSONL 接收快照时拒绝覆盖，改用 --import-corpus。"""
    if conn.execute("SELECT 1 FROM corpus_imports LIMIT 1").fetchone():
        raise ValueError("本库由 JSONL 快照管理；请用 --import-corpus 导入修正版，不能用旧 records 覆盖")
    unique, stats = deduplicate(list(records))
    keep_urls = {canonicalize_url(record.url) for record in unique}
    with conn:
        for (url,) in conn.execute("SELECT url FROM documents").fetchall():
            if url not in keep_urls:
                if conn.execute("SELECT 1 FROM chunks WHERE doc_id=? LIMIT 1", (url,)).fetchone():
                    conn.execute("UPDATE documents SET active=0, index_dirty=1 WHERE url=?", (url,))
                else:
                    conn.execute("DELETE FROM documents WHERE url=?", (url,))
        for record in unique:
            row = {
                "url": canonicalize_url(record.url), "title": clean_title(record.title),
                "source": record.source, "topic": record.topic,
                "academic_year": infer_academic_year(record), "date": record.date,
                "crawled_at": record.crawled_at, "content": record.content,
                "image_urls": json.dumps(record.image_urls, ensure_ascii=False),
                "file_urls": json.dumps(record.file_urls, ensure_ascii=False),
                "column_name": record.column,
            }
            changed = " OR ".join(f"documents.{c} IS NOT excluded.{c}" for c in DOCUMENT_COLS if c != "url")
            conn.execute(
                "INSERT INTO documents (" + ", ".join(DOCUMENT_COLS) + ") VALUES ("
                + ", ".join(":" + c for c in DOCUMENT_COLS) + ") ON CONFLICT(url) DO UPDATE SET "
                + ", ".join(c + "=excluded." + c for c in DOCUMENT_COLS if c != "url")
                + ", index_dirty=CASE WHEN documents.active=0 OR " + changed
                + " THEN 1 ELSE documents.index_dirty END, active=1", row)
    stats["documents"] = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    stats["active_documents"] = conn.execute("SELECT COUNT(*) FROM documents WHERE active=1").fetchone()[0]
    return stats


def log_crawl_run(conn: sqlite3.Connection, column_name: str,
                  started_at: str, finished_at: str,
                  new_count: int = 0, skip_count: int = 0, error_count: int = 0) -> int:
    """写一条抓取审计，返回 run_id。"""
    cur = conn.execute(
        "INSERT INTO crawl_runs (started_at, finished_at, column_name,"
        " new_count, skip_count, error_count) VALUES (?,?,?,?,?,?)",
        (started_at, finished_at, column_name, new_count, skip_count, error_count),
    )
    conn.commit()
    return int(cur.lastrowid)


def log_qa(conn: sqlite3.Connection, question: str, answer: str,
           citations: Optional[list] = None, latency_ms: int = 0,
           created_at: str = "") -> int:
    """写一条问答日志，返回 log_id。"""
    cur = conn.execute(
        "INSERT INTO qa_logs (question, answer, citations, latency_ms, created_at)"
        " VALUES (?,?,?,?,?)",
        (question, answer, json.dumps(citations or [], ensure_ascii=False),
         latency_ms, created_at),
    )
    conn.commit()
    return int(cur.lastrowid)
