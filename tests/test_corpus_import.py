import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.corpus_import import import_corpus, document_quality
from src.db import init_schema, migrate_from_records
from src.crawler import ColumnSpec
from src.storage import Record
from src.main import main


def row(url="https://x.test/a", content="Student service information. " * 20, year=""):
    return dict(url=url, title="Calendar 2026/27", source="x.test", content=content,
                date="2026-10-11", crawled_at="2026-10-11T12:00:00+08:00",
                topic="校历", column="calendar", academic_year=year, error="",
                image_urls=["https://x.test/image.png"], file_urls=["https://x.test/file.pdf"])


class TestCorpusImport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = Path(self.temp.name) / "corpus.jsonl"
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def save(self, rows):
        self.path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return self.path

    def test_01_import_preserves_blank_and_supplied_year_and_metadata(self):
        report = import_corpus(self.save([row(), row("https://x.test/b", "Different body " * 40, "2026-2021")]), self.conn)
        self.assertEqual(report["active_documents"], 2)
        docs = self.conn.execute("SELECT url,academic_year,column_name,file_urls,corpus_sha256 FROM documents ORDER BY url").fetchall()
        self.assertEqual(docs[0][1], "")
        self.assertEqual(docs[1][1], "2026-2021")
        self.assertEqual(docs[0][2], "calendar")
        self.assertEqual(json.loads(docs[0][3]), ["https://x.test/file.pdf"])
        self.assertEqual(docs[0][4], report["sha256"])
        self.assertFalse(report["release_ready"])

    def test_02_reimport_is_idempotent_and_does_not_dirty_index(self):
        import_corpus(self.save([row()]), self.conn)
        self.conn.execute("UPDATE documents SET index_dirty=0")
        self.conn.commit()
        report = import_corpus(self.path, self.conn)
        self.assertEqual((report["inserted"], report["updated"], report["unchanged"]), (0, 0, 1))
        self.assertEqual(self.conn.execute("SELECT index_dirty FROM documents").fetchone()[0], 0)

    def test_03_replace_preserves_referenced_old_document_as_inactive(self):
        old = row("https://x.test/old", "Old content " * 40)
        import_corpus(self.save([row(), old]), self.conn)
        self.conn.execute("INSERT INTO chunks (chunk_id,doc_id,text) VALUES ('old','https://x.test/old','old')")
        self.conn.commit()
        report = import_corpus(self.save([row()]), self.conn)
        self.assertEqual((report["active_documents"], report["total_documents"], report["retained_inactive"]), (1, 2, 1))
        self.assertEqual(self.conn.execute("SELECT active,index_dirty FROM documents WHERE url='https://x.test/old'").fetchone(), (0, 1))
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_04_replace_removes_only_unreferenced_document(self):
        import_corpus(self.save([row(), row("https://x.test/old", "Old content " * 40)]), self.conn)
        report = import_corpus(self.save([row()]), self.conn)
        self.assertEqual((report["total_documents"], report["removed_unreferenced"]), (1, 1))

    def test_05_metadata_change_marks_existing_chunk_stale(self):
        import_corpus(self.save([row()]), self.conn)
        self.conn.execute("INSERT INTO chunks (chunk_id,doc_id,text) VALUES ('a','https://x.test/a','old')")
        self.conn.execute("UPDATE documents SET index_dirty=0")
        self.conn.commit()
        modified = row(year="2026-2027")
        report = import_corpus(self.save([modified]), self.conn)
        self.assertEqual(report["updated"], 1)
        self.assertEqual(self.conn.execute("SELECT index_dirty FROM documents").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], 1)

    def test_06_invalid_row_does_not_change_previous_snapshot(self):
        import_corpus(self.save([row()]), self.conn)
        bad = row("https://x.test/b")
        bad["file_urls"] = "not a list"
        with self.assertRaises(ValueError):
            import_corpus(self.save([row(), bad]), self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM corpus_imports").fetchone()[0], 1)

    def test_07_duplicate_url_and_content_are_rejected(self):
        for rows in ([row(), row(content="different")], [row(), row("https://x.test/b")]):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    import_corpus(self.save(rows), self.conn)

    def test_08_empty_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):
            import_corpus(self.save([]), self.conn)

    def test_09_upgrade_old_documents_table_preserves_data(self):
        self.conn.execute("CREATE TABLE documents (url TEXT PRIMARY KEY,title TEXT,source TEXT,topic TEXT,academic_year TEXT,date TEXT,crawled_at TEXT,content TEXT,image_urls TEXT,file_urls TEXT)")
        self.conn.execute("INSERT INTO documents (url,content) VALUES ('https://x.test/a','original')")
        self.conn.commit()
        init_schema(self.conn)
        init_schema(self.conn)
        self.assertEqual(self.conn.execute("SELECT content,active,column_name FROM documents").fetchone(), ("original", 1, ""))

    def test_10_sql_error_rolls_back_rows_and_audit(self):
        import_corpus(self.save([row()]), self.conn)
        self.conn.execute("CREATE TRIGGER fail_row BEFORE INSERT ON documents WHEN NEW.url='https://x.test/b' BEGIN SELECT RAISE(ABORT,'forced failure'); END")
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            import_corpus(self.save([row(content="changed"), row("https://x.test/b", "other content")]), self.conn)
        self.assertEqual(self.conn.execute("SELECT content FROM documents").fetchone()[0], row()["content"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM corpus_imports").fetchone()[0], 1)

    def test_11_records_migration_cannot_overwrite_received_snapshot(self):
        import_corpus(self.save([row()]), self.conn)
        with self.assertRaises(ValueError):
            migrate_from_records([], self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM documents WHERE active=1").fetchone()[0], 1)

    def test_12_document_quality_uses_active_snapshot(self):
        import_corpus(self.save([row(year="2026-2021")]), self.conn)
        report = document_quality(self.conn, [ColumnSpec(name="calendar", seeds=["https://x.test/a"])])
        self.assertEqual(report["source"], "documents.active=1")
        self.assertEqual(report["seed_success"], 1)
        self.assertEqual(report["integrity"], ["ok"])
        self.assertEqual(len(report["suspicious_years"]), 1)
        self.assertFalse(report["release_ready"])

    def test_13_cli_import_quality_and_export_guard(self):
        db = str(Path(self.temp.name) / "test.db")
        output = str(Path(self.temp.name) / "quality.json")
        self.save([row()])
        self.assertEqual(main(["--db", db, "--import-corpus", str(self.path)]), 0)
        self.assertEqual(main(["--db", db, "--import-corpus", str(self.path)]), 0)
        self.assertEqual(main(["--db", db, "--quality", "--quality-source", "documents", "--column", "calendar", "--quality-output", output]), 1)  # 官方 calendar 种子未在假数据中
        self.assertEqual(json.loads(Path(output).read_text(encoding="utf-8"))["source"], "documents.active=1")
        original = self.path.read_bytes()
        self.assertEqual(main(["--db", db, "--export", str(self.path)]), 1)
        self.assertEqual(main(["--db", db, "--migrate"]), 1)
        self.assertEqual(self.path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
