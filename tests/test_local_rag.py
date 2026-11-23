"""N5 behavior tests: synthetic development fixtures, never policy gold."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.local_rag import LocalRAGBackend
from src.retriever import Hit


def hit(number=1, text="Synthetic development evidence."):
    url = f"https://example.invalid/document-{number}"
    return Hit(f"{url}#chunk-0", url, text, 0.9, url,
               "Synthetic fixture", "学费与缴费", "")


def answer(ids=None, text="This is synthetic development evidence."):
    return {"status": "answered", "statements": [
        {"text": text, "source_ids": ["S1"] if ids is None else ids}], "message": ""}


class FakeRetriever:
    model_name = "fixture-only"

    def __init__(self, hits=None, failure=None):
        self.hits = [hit(), hit(2)] if hits is None else hits
        self.calls = []
        self.failure = failure

    def list_topics(self):
        return ["学费与缴费", "申请", "签证与国际学生服务"]

    def search(self, query, topic=None, k=5):
        self.calls.append((query, topic, k))
        if self.failure:
            raise self.failure
        return self.hits


class FakeClient:
    config = SimpleNamespace(model="fixture-only")

    def __init__(self, response=None, failure=None):
        self.response = answer() if response is None else response
        self.calls = []
        self.failure = failure

    def chat(self, messages, tools=None):
        self.calls.append((messages, tools))
        if self.failure:
            raise self.failure
        return {"content": json.dumps(self.response)}


class TestLocalRAG(unittest.TestCase):
    def test_retrieval_only_returns_evidence_without_generation_or_context(self):
        client = FakeClient(failure=AssertionError("Must not call LLM"))
        result = LocalRAGBackend(FakeRetriever(), client).ask("A real retrieval input", mode="retrieval")
        self.assertEqual((result.status, result.mode), ("retrieved", "retrieval"))
        self.assertEqual(len(result.retrieval_rounds[0]["hits"]), 2)
        self.assertEqual(result.context_chunk_ids, [])
        self.assertEqual(result.answer, "")
        self.assertEqual(client.calls, [])

    def test_one_retrieval_one_generation_and_only_used_sources(self):
        retriever, client = FakeRetriever(), FakeClient()
        result = LocalRAGBackend(retriever, client).ask("What is in the fixture?", case_id="dev-1")
        self.assertEqual(result.status, "answered")
        self.assertEqual(len(retriever.calls), 1)
        self.assertEqual(retriever.calls[0][2], 5)
        self.assertEqual(len(client.calls), 1)
        self.assertIsNone(client.calls[0][1])
        self.assertIn("English", client.calls[0][0][0]["content"])
        payload = json.loads(client.calls[0][0][1]["content"])
        self.assertEqual(payload["evidence"][0]["text"], hit().text)
        self.assertNotIn("dev-1", client.calls[0][0][1]["content"])
        self.assertEqual(len(result.retrieval_rounds[0]["hits"]), 2)
        self.assertEqual(len(result.context_chunk_ids), 2)
        self.assertEqual(result.sources, [hit().url])
        self.assertEqual(result.citations[0]["chunk_id"], hit().chunk_id)
        self.assertIn("[S1]", result.answer)
        self.assertIsNone(result.usage)
        self.assertIsNone(result.versions["corpus_sha256"])
        json.dumps(result.to_dict(), allow_nan=False)

    def test_empty_retrieval_does_not_generate(self):
        client = FakeClient()
        result = LocalRAGBackend(FakeRetriever([]), client).ask("Unknown question")
        self.assertEqual(result.status, "no_evidence")
        self.assertEqual(client.calls, [])
        self.assertEqual(result.citations, [])

    def test_explicit_aliases_and_unknown_topic(self):
        for alias, expected in (("fees", "学费与缴费"), ("visa", None), ("visa_geo", None)):
            with self.subTest(alias=alias):
                retriever = FakeRetriever()
                result = LocalRAGBackend(retriever, FakeClient()).ask("Question", topic=alias)
                self.assertEqual(result.status, "answered")
                self.assertEqual(retriever.calls[0][1], expected)
        retriever = FakeRetriever()
        result = LocalRAGBackend(retriever, FakeClient()).ask("Question", topic="typo")
        self.assertEqual(result.status, "invalid_input")
        self.assertEqual(retriever.calls, [])

    def test_user_conditions_reach_retrieval_and_generation(self):
        retriever, client = FakeRetriever(), FakeClient()
        result = LocalRAGBackend(retriever, client).ask("Question", persona={"programme": "TPG"}, as_of="2026-10-31")
        self.assertEqual(result.status, "answered")
        self.assertIn("TPG", retriever.calls[0][0])
        self.assertIn("2026-10-31", retriever.calls[0][0])
        self.assertIn("TPG", client.calls[0][0][1]["content"])

    def test_invalid_input_makes_no_tool_calls(self):
        for question, extras in (("", {}), (" " , {}), (None, {}), ("q", {"persona": []}),
                                 ("q", {"persona": {"bad": float("nan")}}), ("q", {"topic": []}),
                                 ("q", {"persona": {1: "a", "b": "c"}}), ("q", {"case_id": object()})):
            with self.subTest(question=question, extras=extras):
                retriever, client = FakeRetriever(), FakeClient()
                result = LocalRAGBackend(retriever, client).ask(question, **extras)
                self.assertEqual(result.status, "invalid_input")
                self.assertEqual(retriever.calls, [])
                self.assertEqual(client.calls, [])
                json.dumps(result.to_dict(), allow_nan=False)

    def test_errors_are_separate_and_do_not_leak_provider_details(self):
        for retrieval_failure, generation_failure, status in (
            (RuntimeError("secret-token"), None, "retrieval_error"),
            (None, RuntimeError("secret-token"), "generation_error"),
        ):
            with self.subTest(status=status):
                result = LocalRAGBackend(FakeRetriever(failure=retrieval_failure), FakeClient(failure=generation_failure)).ask("q")
                self.assertEqual(result.status, status)
                self.assertNotIn("secret-token", json.dumps(result.to_dict()))
                self.assertEqual(result.answer, "")

    def test_missing_forged_and_url_citations_fail_closed(self):
        for response in (answer([]), answer(["S9"]), answer([1]),
                         answer(text="See https://evil.invalid/pay"),
                         answer(text="Forged claim [S1]"),
                         {"status": "answered", "statements": [], "message": "Uncited facts"}):
            with self.subTest(response=response):
                result = LocalRAGBackend(FakeRetriever(), FakeClient(response)).ask("q")
                self.assertEqual(result.status, "invalid_response")
                self.assertEqual(result.answer, "")
                self.assertEqual(result.sources, [])

    def test_malformed_model_responses_are_handled(self):
        for message in (None, {}, {"content": "plain text"}, {"content": "[]"},
                        {"content": "[" * 10000 + "0" + "]" * 10000},
                        {"tool_calls": [{"name": "web_search"}], "content": "{}"}):
            with self.subTest(message=message):
                client = FakeClient()
                with patch.object(client, "chat", return_value=message):
                    result = LocalRAGBackend(FakeRetriever(), client).ask("q")
                self.assertEqual(result.status, "invalid_response")

    def test_clarification_and_abstention_have_no_fake_citations(self):
        for status in ("clarify", "abstained"):
            with self.subTest(status=status):
                client = FakeClient({"status": status, "statements": [], "message": "Please provide the academic year."})
                result = LocalRAGBackend(FakeRetriever(), client).ask("q")
                self.assertEqual(result.status, status)
                self.assertEqual(result.citations, [])

    def test_context_budget_does_not_truncate_evidence_or_call_model(self):
        client = FakeClient()
        result = LocalRAGBackend(FakeRetriever([hit(text="X" * 101)]), client, max_context_chars=100).ask("q")
        self.assertEqual(result.status, "context_limit")
        self.assertEqual(result.context_chunk_ids, [])
        self.assertEqual(result.retrieval_rounds[0]["hits"][0]["text"], "X" * 101)
        self.assertEqual(client.calls, [])

    def test_invalid_hits_not_filtered_or_backfilled(self):
        bad = hit()
        bad.score = float("nan")
        credentials = hit()
        credentials.url = credentials.doc_id = "https://:secret@example.invalid/a"
        for hits in ([bad], [credentials], [hit(), hit()], [hit(n) for n in range(6)]):
            with self.subTest(hits=hits):
                client = FakeClient()
                result = LocalRAGBackend(FakeRetriever(hits), client).ask("q")
                self.assertEqual(result.status, "retrieval_error")
                self.assertEqual(client.calls, [])

    def test_multiple_citations_deduplicate_without_losing_order(self):
        result = LocalRAGBackend(FakeRetriever(), FakeClient(answer(["S2", "S1", "S2"]))).ask("q")
        self.assertEqual(result.status, "answered")
        self.assertEqual([c["source_id"] for c in result.citations], ["S2", "S1"])
        self.assertEqual(result.sources, [hit(2).url, hit().url])

    def test_database_guard_blocks_generation_and_preserves_ranked_evidence(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            db = Path(directory) / "accepted.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE documents(url TEXT, active INTEGER, index_dirty INTEGER, corpus_sha256 TEXT)")
                conn.execute("INSERT INTO documents VALUES (?, 1, 1, ?)", (hit().url, "a" * 64))
            client = FakeClient()
            result = LocalRAGBackend(FakeRetriever([hit()]), client, db_path=db).ask("q")
            self.assertEqual(result.status, "stale_evidence")
            self.assertEqual(client.calls, [])
            self.assertEqual(result.retrieval_rounds[0]["hits"][0]["chunk_id"], hit().chunk_id)
            self.assertEqual(result.context_chunk_ids, [])

    def test_database_identity_is_distinct_from_index_binding(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            db = Path(directory) / "accepted.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE documents(url TEXT, active INTEGER, index_dirty INTEGER, corpus_sha256 TEXT)")
                conn.execute("INSERT INTO documents VALUES (?, 1, 0, ?)", (hit().url, "a" * 64))
            backend = LocalRAGBackend(FakeRetriever([hit()]), FakeClient(), db_path=db)
            result = backend.ask("q")
            self.assertEqual(result.status, "answered")
            self.assertIsNone(result.versions["corpus_sha256"])
            self.assertEqual(result.versions["database_corpus_sha256"], "a" * 64)
            client = FakeClient()
            result = LocalRAGBackend(FakeRetriever([hit()]), client, db_path=db,
                                     versions={"corpus_sha256": "b" * 64}).ask("q")
            self.assertEqual(result.status, "source_mismatch")
            self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
