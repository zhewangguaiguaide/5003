"""N5 artifact and SQLite guards; synthetic fixtures, no real model or policy."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.local_sources import E5_MODEL, LocalSourceError, load_retriever, validate_hits
from src.retriever import Hit


def hit(url="https://example.test/a"):
    return Hit("chunk-a", url, "Synthetic evidence", 0.8, url, "Fixture", "Topic", "")


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.index_bytes = b"synthetic-index-stand-in"
        (self.root / "index.faiss").write_bytes(self.index_bytes)
        self.metadata = {
            "model": E5_MODEL,
            "dimension": 3,
            "chunks": [{"chunk_id": "c1", "text": "Synthetic evidence", "url": "https://example.test/a"}],
        }
        self.write_metadata()
        self.retriever = SimpleNamespace(index=SimpleNamespace(d=3, ntotal=1))
        self.model = Mock()
        self.model.get_sentence_embedding_dimension.return_value = 3
        self.model_factory = Mock(return_value=self.model)
        self.addCleanup(patch.stopall)
        patch("src.local_sources.Retriever", return_value=self.retriever).start()
        patch("src.local_sources.LocalEncoder", self.model_factory).start()

    def write_metadata(self):
        (self.root / "chunks.json").write_text(json.dumps(self.metadata), encoding="utf-8")

    def test_loader_records_actual_hashes_and_unknown_provenance(self):
        retriever, versions, warnings = load_retriever(self.root)
        self.assertIs(retriever._model, self.model)
        self.model_factory.assert_called_once_with(E5_MODEL)
        self.assertEqual(versions["index_sha256"], hashlib.sha256(self.index_bytes).hexdigest())
        self.assertEqual(versions["chunks_sha256"], hashlib.sha256((self.root / "chunks.json").read_bytes()).hexdigest())
        self.assertIsNone(versions["corpus_sha256"])
        self.assertIsNone(versions["model_revision"])
        self.assertTrue(warnings)

    def test_wrong_model_is_rejected_before_loading_model(self):
        self.metadata["model"] = "other-model"
        self.write_metadata()
        with self.assertRaises(LocalSourceError) as error:
            load_retriever(self.root)
        self.assertEqual(error.exception.code, "index_mismatch")
        self.model_factory.assert_not_called()

    def test_bound_model_and_index_hashes_are_enforced(self):
        folder = self.root / "model"
        folder.mkdir()
        (folder / "weights").write_bytes(b"synthetic-model")
        self.metadata.update({
            "provenance_version": 1, "corpus_sha256": "a" * 64, "model_revision": "b" * 40,
            "index_sha256": hashlib.sha256(self.index_bytes).hexdigest(),
            "query_prefix": "query: ", "passage_prefix": "passage: ", "normalize_embeddings": True,
            "model_files_sha256": {"weights": hashlib.sha256(b"synthetic-model").hexdigest()},
            "database_chunk_binding": True,
        })
        self.write_metadata()
        _, versions, _ = load_retriever(self.root, model_path=folder)
        self.assertEqual(versions["corpus_sha256"], "a" * 64)
        self.assertEqual(versions["model_revision"], "b" * 40)
        self.assertTrue(versions["database_chunk_binding"])
        (folder / "weights").write_bytes(b"wrong-model")
        with self.assertRaises(LocalSourceError) as error:
            load_retriever(self.root, model_path=folder)
        self.assertEqual(error.exception.code, "index_mismatch")


    def test_metadata_and_vector_dimension_or_count_mismatch(self):
        for dimension, count in ((4, 1), (3, 2)):
            with self.subTest(dimension=dimension, count=count):
                self.retriever.index.d = dimension
                self.retriever.index.ntotal = count
                with self.assertRaises(LocalSourceError) as error:
                    load_retriever(self.root)
                self.assertEqual(error.exception.code, "index_mismatch")

    def test_actual_model_dimension_mismatch(self):
        self.model.get_sentence_embedding_dimension.return_value = 7
        with self.assertRaises(LocalSourceError) as error:
            load_retriever(self.root)
        self.assertEqual(error.exception.code, "index_mismatch")

    def test_duplicate_chunk_ids_rejected(self):
        self.metadata["chunks"] *= 2
        self.write_metadata()
        with self.assertRaises(LocalSourceError) as error:
            load_retriever(self.root)
        self.assertEqual(error.exception.code, "index_mismatch")

    def test_missing_files_and_bad_json_are_safe(self):
        (self.root / "chunks.json").write_text("not json", encoding="utf-8")
        with self.assertRaises(LocalSourceError) as error:
            load_retriever(self.root)
        self.assertEqual(error.exception.code, "index_unavailable")
        (self.root / "index.faiss").unlink()
        with self.assertRaises(LocalSourceError):
            load_retriever(self.root)

    def test_model_load_error_does_not_expose_internal_details(self):
        self.model_factory.side_effect = OSError("secret cache path /private/token")
        with self.assertRaises(LocalSourceError) as error:
            load_retriever(self.root)
        self.assertEqual(error.exception.code, "model_unavailable")
        self.assertNotIn("token", str(error.exception))

    def test_files_changed_during_loading_are_rejected(self):
        def change_file(*args, **kwargs):
            (self.root / "index.faiss").write_bytes(b"new index")
            return self.model
        self.model_factory.side_effect = change_file
        with self.assertRaises(LocalSourceError) as error:
            load_retriever(self.root)
        self.assertEqual(error.exception.code, "index_mismatch")


class DocumentGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "documents # 测试.db"
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE documents (url TEXT PRIMARY KEY, active INTEGER, index_dirty INTEGER, corpus_sha256 TEXT)")
            connection.execute("INSERT INTO documents VALUES (?, 1, 0, ?)", (hit().url, "a" * 64))

    def update(self, sql, args=()):
        with sqlite3.connect(self.path) as connection:
            connection.execute(sql, args)

    def test_valid_hits_read_database_without_mutating_files_or_hits(self):
        hits = [hit()]
        before = self.path.read_bytes()
        self.assertEqual(validate_hits(self.path, hits), "a" * 64)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(hits, [hit()])

    def test_inactive_dirty_or_missing_evidence_fails_whole_request(self):
        for active, dirty in ((0, 0), (1, 1)):
            with self.subTest(active=active, dirty=dirty):
                self.update("UPDATE documents SET active=?, index_dirty=?", (active, dirty))
                with self.assertRaises(LocalSourceError) as error:
                    validate_hits(self.path, [hit()])
                self.assertEqual(error.exception.code, "stale_evidence")
        self.update("UPDATE documents SET active=1, index_dirty=0")
        hits = [hit(), hit("https://example.test/missing")]
        with self.assertRaises(LocalSourceError) as error:
            validate_hits(self.path, hits)
        self.assertEqual(error.exception.code, "stale_evidence")
        self.assertEqual(len(hits), 2)

    def test_mixed_snapshots_are_rejected(self):
        other = hit("https://example.test/b")
        self.update("INSERT INTO documents VALUES (?, 1, 0, ?)", (other.url, "b" * 64))
        with self.assertRaises(LocalSourceError) as error:
            validate_hits(self.path, [hit(), other])
        self.assertEqual(error.exception.code, "index_mismatch")

    def test_unknown_sha_is_not_fabricated(self):
        self.update("UPDATE documents SET corpus_sha256='' ")
        self.assertIsNone(validate_hits(self.path, [hit()]))

    def test_inconsistent_hit_identity_rejected(self):
        candidate = hit()
        candidate.doc_id = "https://example.test/other"
        with self.assertRaises(LocalSourceError) as error:
            validate_hits(self.path, [candidate])
        self.assertEqual(error.exception.code, "stale_evidence")

    def test_missing_database_is_not_created(self):
        missing = self.path.parent / "missing.db"
        with self.assertRaises(LocalSourceError) as error:
            validate_hits(missing, [hit()])
        self.assertEqual(error.exception.code, "database_unavailable")
        self.assertFalse(missing.exists())

    def test_missing_schema_is_reported_without_raw_sql_error(self):
        self.update("DROP TABLE documents")
        with self.assertRaises(LocalSourceError) as error:
            validate_hits(self.path, [hit()])
        self.assertEqual(error.exception.code, "database_unavailable")
        self.assertNotIn("no such table", str(error.exception))


if __name__ == "__main__":
    unittest.main()
