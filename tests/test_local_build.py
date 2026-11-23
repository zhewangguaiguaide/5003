"""Snapshot/provenance guards use synthetic data, no model download."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_local_index import verify_snapshot
from src.corpus_import import import_corpus
from src.local_sources import LocalSourceError, validate_hits
from src.retriever import Hit
from tests.test_corpus_import import row


class TestBuildGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.corpus = self.root / "corpus.jsonl"
        self.db = self.root / "source.db"
        self.record = row()
        self.corpus.write_text(json.dumps(self.record) + "\n", encoding="utf-8")
        with sqlite3.connect(self.db) as conn:
            import_corpus(self.corpus, conn)

    def test_all_fields_and_sha_checked_without_changing_source(self):
        before = self.db.read_bytes()
        records, sha = verify_snapshot(self.corpus, self.db)
        self.assertEqual(records, [self.record])
        self.assertEqual(sha, hashlib.sha256(self.corpus.read_bytes()).hexdigest())
        self.assertEqual(self.db.read_bytes(), before)

    def test_same_sha_but_modified_content_is_rejected(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE documents SET content='Different text'")
        with self.assertRaisesRegex(ValueError, "field mismatch"):
            verify_snapshot(self.corpus, self.db)

    def test_changed_jsonl_bytes_require_new_version(self):
        self.corpus.write_text(self.corpus.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "SHA"):
            verify_snapshot(self.corpus, self.db)

    def test_bound_hit_text_must_match_runtime_chunk(self):
        evidence = Hit("c1", self.record["url"], "Expected text", 0.9, self.record["url"], "Title", "Topic", "")
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE documents SET index_dirty=0")
            conn.execute("INSERT INTO chunks(chunk_id,doc_id,ord,text) VALUES (?,?,0,?)",
                         ("c1", self.record["url"], "Expected text"))
        self.assertIsNotNone(validate_hits(self.db, [evidence], require_chunks=True))
        evidence.text = "Mismatched index text"
        with self.assertRaises(LocalSourceError) as error:
            validate_hits(self.db, [evidence], require_chunks=True)
        self.assertEqual(error.exception.code, "stale_evidence")
