"""存储层：幂等写入 + 已存在查询。

接口即为 Harness 的验收面（见 docs/Harness开发指导.md 的 eval 设计）：
- exists(url) -> bool    : 停止条件的判断依据，被 eval 计数
- upsert(record) -> bool : 返回 True 表示新记录，False 表示已存在被更新
- count() / all_records()
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Record:
    """一条清洗后的 FAQ/内容记录。"""

    url: str
    title: str = ""
    source: str = ""
    content: str = ""
    date: str = ""            # 内容发布日期（ISO），无则回落为抓取时间
    crawled_at: str = ""      # 抓取时间（ISO）
    image_urls: List[str] = field(default_factory=list)
    file_urls: List[str] = field(default_factory=list)
    error: str = ""           # 抓取失败时保留错误，便于 Loop 阶段修复
    topic: str = ""
    column: str = ""

    def to_row(self) -> Dict[str, Any]:
        row = asdict(self)
        row["image_urls"] = json.dumps(self.image_urls, ensure_ascii=False)
        row["file_urls"] = json.dumps(self.file_urls, ensure_ascii=False)
        return row


class SQLiteStorage:
    """生产用存储：url 为主键，天然幂等。"""

    def __init__(self, path: str = "data/cityu_faq.db") -> None:
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                url TEXT PRIMARY KEY,
                title TEXT, source TEXT, content TEXT,
                date TEXT, crawled_at TEXT,
                image_urls TEXT, file_urls TEXT,
                error TEXT, topic TEXT, column_name TEXT
            )
            """
        )
        self._conn.commit()
        self.exists_calls = 0

    def exists(self, url: str) -> bool:
        self.exists_calls += 1
        cur = self._conn.execute("SELECT 1 FROM records WHERE url = ? AND COALESCE(error, '') = '' LIMIT 1", (url,))
        return cur.fetchone() is not None

    def upsert(self, record: Record) -> bool:
        is_new = not self.exists(record.url)
        row = record.to_row()
        self._conn.execute(
            """
            INSERT INTO records (url, title, source, content, date, crawled_at,
                                 image_urls, file_urls, error, topic, column_name)
            VALUES (:url, :title, :source, :content, :date, :crawled_at,
                    :image_urls, :file_urls, :error, :topic, :column)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title, source=excluded.source, content=excluded.content,
                date=excluded.date, crawled_at=excluded.crawled_at,
                image_urls=excluded.image_urls, file_urls=excluded.file_urls,
                error=excluded.error, topic=excluded.topic, column_name=excluded.column_name
            """,
            row,
        )
        self._conn.commit()
        return is_new

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    def all_records(self) -> List[Record]:
        cols = ("url", "title", "source", "content", "date", "crawled_at",
                "image_urls", "file_urls", "error", "topic", "column_name")
        out = []
        for row in self._conn.execute("SELECT * FROM records"):
            data = dict(zip(cols, row))
            data["image_urls"] = json.loads(data["image_urls"] or "[]")
            data["file_urls"] = json.loads(data["file_urls"] or "[]")
            data["column"] = data.pop("column_name")
            out.append(Record(**data))
        return out

    def close(self) -> None:
        self._conn.close()


class MockStorage:
    """测试用存储。

    当 exists_after 被设置时，exists() 会在第 exists_after 次调用时返回 True，
    用于验证"停止条件生效且被检查了恰好 N 次"（eval 项 6）。
    """

    def __init__(self, exists_after: Optional[int] = None) -> None:
        self.rows: Dict[str, Record] = {}
        self.exists_calls = 0
        self.exists_after = exists_after
        self.upsert_calls = 0

    def exists(self, url: str) -> bool:
        self.exists_calls += 1
        if self.exists_after is not None and self.exists_calls >= self.exists_after:
            return True
        return url in self.rows and not self.rows[url].error

    def upsert(self, record: Record) -> bool:
        self.upsert_calls += 1
        is_new = record.url not in self.rows
        self.rows[record.url] = record
        return is_new

    def count(self) -> int:
        return len(self.rows)

    def all_records(self) -> List[Record]:
        return list(self.rows.values())

    def close(self) -> None:  # 接口对齐
        pass
