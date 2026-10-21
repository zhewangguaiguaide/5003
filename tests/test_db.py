import sqlite3
import unittest

from src.db import init_schema, migrate_from_records, log_crawl_run, log_qa
from src.storage import Record


class TestNormalizedSchema(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def _tables(self):
        return {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}

    def _indexes(self):
        return {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}

    def test_01_schema_creates_four_tables_and_indexes(self):
        init_schema(self.conn)
        self.assertTrue({"documents", "chunks", "crawl_runs", "qa_logs"} <= self._tables())
        self.assertIn("idx_documents_topic_year", self._indexes())
        self.assertIn("idx_documents_crawled_at", self._indexes())
        self.assertIn("idx_chunks_doc", self._indexes())

    def test_02_init_schema_is_idempotent(self):
        init_schema(self.conn)
        init_schema(self.conn)  # 第二次不报错
        self.assertIn("documents", self._tables())

    def test_03_migration_sinks_academic_year_and_canonicalizes(self):
        records = [
            Record(url="https://x.test/a/?utm_source=z", title="Calendar 2026/27",
                   content="Dates " * 50, topic="校历与重要日期", column="calendar"),
            Record(url="https://x.test/a/", title="Calendar 2026/27 alias",
                   content="Dates " * 50, topic="校历与重要日期", column="calendar"),
            Record(url="https://x.test/b", title="Fees", content="Fee table " * 50,
                   topic="学费与缴费", column="fees"),
        ]
        init_schema(self.conn)
        stats = migrate_from_records(records, self.conn)
        self.assertEqual(stats["documents"], 2)  # 指纹去重后剩 2 条
        rows = self.conn.execute(
            "SELECT url, academic_year, topic FROM documents ORDER BY url").fetchall()
        self.assertEqual(rows[0][0], "https://x.test/a")  # canonical：去尾斜杠、去 utm
        self.assertEqual(rows[0][1], "2026-2027")          # academic_year 已下沉
        self.assertEqual(rows[0][2], "校历与重要日期")
        self.assertEqual(rows[1][1], "")                    # 无学年留空不猜测

    def test_04_migration_is_idempotent(self):
        records = [Record(url="https://x.test/a", title="T", content="body " * 80)]
        init_schema(self.conn)
        migrate_from_records(records, self.conn)
        stats = migrate_from_records(records, self.conn)  # 重跑不翻倍
        self.assertEqual(stats["documents"], 1)

    def test_05_crawl_runs_and_qa_logs_accept_rows(self):
        init_schema(self.conn)
        run_id = log_crawl_run(self.conn, "fees", "2026-10-10T03:30", "2026-10-10T03:39",
                               new_count=4, skip_count=3, error_count=2)
        self.assertGreaterEqual(run_id, 1)
        log_id = log_qa(self.conn, "学费怎么交？", "……", citations=["https://x.test/b"],
                        latency_ms=1230, created_at="2026-10-11T15:00")
        self.assertGreaterEqual(log_id, 1)
        row = self.conn.execute(
            "SELECT column_name, error_count FROM crawl_runs").fetchone()
        self.assertEqual(row, ("fees", 2))
        cites = self.conn.execute("SELECT citations FROM qa_logs").fetchone()[0]
        self.assertIn("x.test/b", cites)

    def test_06_quality_refresh_prunes_only_unreferenced_documents(self):
        init_schema(self.conn)
        records = [Record(url='https://x/a', content='valid body ' * 50),
                   Record(url='https://x/b', content='another body ' * 50)]
        migrate_from_records(records, self.conn)
        self.conn.execute("INSERT INTO chunks (chunk_id, doc_id, text) VALUES ('c', 'https://x/a', 'chunk')")
        self.conn.commit()
        migrate_from_records([], self.conn)
        self.assertEqual(self.conn.execute('SELECT url FROM documents').fetchall(), [('https://x/a',)])
        migrate_from_records([records[0]], self.conn)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
