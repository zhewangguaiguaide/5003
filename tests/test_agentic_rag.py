"""Synthetic N7 behavior and failure fixtures; no policy gold or network."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.agentic_rag import AgentBudget, AgenticRAGBackend
from src.retriever import Hit


def hit(n=1, text=None):
    url = f"https://example.invalid/fixture-{n}"
    return Hit(url + "#chunk-0", url, text or f"Synthetic fixture {n}.",
               0.8, url, "Synthetic fixture", "学费与缴费", "")


def retrieve(query="second detail", topic=None):
    return {"action": "retrieve", "reason": "The second fact is missing.",
            "missing_information": ["Second fact"], "query": query, "topic": topic}


def final(action="answer", ids=None):
    status = {"answer": "answered", "clarify": "clarify", "abstain": "abstained"}[action]
    return {"action": action, "reason": "A short operational explanation.",
            "missing_information": [] if action == "answer" else ["Applicable year"],
            "response": {"status": status, "statements": [
                {"text": "Synthetic fixture statement.", "source_ids": ids or ["S1"]}
            ] if action == "answer" else [],
                "message": "" if action == "answer" else "Please provide the applicable year."}}


class Retriever:
    model_name = "synthetic"

    def __init__(self, *rounds):
        self.rounds = list(rounds) or [[hit()]]
        self.calls = []

    def list_topics(self):
        return ["学费与缴费", "申请", "注册与学籍"]

    def search(self, query, topic=None, k=5):
        self.calls.append((query, topic, k))
        result = self.rounds[min(len(self.calls) - 1, len(self.rounds) - 1)]
        if isinstance(result, Exception):
            raise result
        return result


class Client:
    config = SimpleNamespace(model="synthetic")

    def __init__(self, *responses, callback=None, review=None):
        self.responses = list(responses) or [final()]
        self.calls = []
        self.callback = callback
        self.review = review
        self.decision_count = 0

    def chat(self, messages):
        payload = json.loads(messages[-1]["content"])
        self.calls.append(payload)
        if self.callback:
            self.callback()
        if payload.get("task") == "review_answer":
            response = self.review if self.review is not None else {
                "verdict": "accept", "requirements": [{"request": "Synthetic request", "covered": True}],
                "unsupported_statements": [], "missing_information": [], "reason": "Supported synthetic fixture."}
        else:
            response = self.responses[self.decision_count]
            self.decision_count += 1
        if isinstance(response, Exception):
            raise response
        return {"content": json.dumps(response)}


class Clock:
    now = 0

    def __call__(self):
        return self.now


class TestAgenticRAG(unittest.TestCase):
    def run_backend(self, retriever=None, client=None, **kwargs):
        return AgenticRAGBackend(retriever or Retriever(), client or Client(), **kwargs).ask("Original question")

    def test_sufficient_evidence_stops_after_one_round(self):
        retriever, client = Retriever(), Client()
        result = self.run_backend(retriever, client)
        self.assertEqual((result.status, result.stop_reason), ("answered", "evidence_sufficient"))
        self.assertEqual((len(retriever.calls), len(client.calls)), (1, 2))
        self.assertEqual(result.mode, "agentic_rag")
        self.assertEqual(result.citations[0]["chunk_id"], hit().chunk_id)
        self.assertEqual(result.budget["used"]["llm_calls"], 2)
        self.assertEqual(result.answer_reviews[0]["verdict"], "accept")

    def test_multi_hop_combines_evidence_with_stable_ids(self):
        retriever = Retriever([hit()], [hit(2), hit()])
        client = Client(retrieve(), final(ids=["S2", "S1"]))
        result = self.run_backend(retriever, client)
        self.assertEqual(result.status, "answered")
        self.assertEqual([x["round"] for x in result.retrieval_rounds], [1, 2])
        self.assertEqual(result.context_chunk_ids, [hit().chunk_id, hit(2).chunk_id])
        self.assertEqual([c["chunk_id"] for c in result.citations], [hit(2).chunk_id, hit().chunk_id])
        self.assertEqual([e["source_id"] for e in client.calls[1]["evidence"]], ["S1", "S2"])
        self.assertTrue(all(c[2] == 5 for c in retriever.calls))
        # First-round ranking remains separate from the final cumulative context.
        self.assertEqual(len(result.retrieval_rounds[0]["hits"]), 1)
        self.assertEqual(len(client.calls[1]["history"]), 2)

    def test_query_rewrite_and_topic_broadening_preserve_user_conditions(self):
        retriever, client = Retriever([hit()], [hit(2)]), Client(retrieve(topic="visa"), final())
        result = AgenticRAGBackend(retriever, client).ask(
            "Original", topic="fees", persona={"programme": "TPG"}, as_of="2026-11-18", case_id="external-case-id")
        self.assertEqual(result.status, "answered")
        self.assertEqual([c[1] for c in retriever.calls], ["学费与缴费", None])
        self.assertTrue(all("TPG" in c[0] and "2026-11-18" in c[0] for c in retriever.calls))
        self.assertEqual(client.calls[1]["input"]["query"], "Original")
        self.assertNotIn("external-case-id", json.dumps(client.calls))

    def test_clarification_and_resume_are_stateless(self):
        retriever, client = Retriever(), Client(final("clarify"), final())
        backend = AgenticRAGBackend(retriever, client)
        first = backend.ask("Original")
        self.assertEqual((first.status, first.stop_reason), ("clarify", "needs_clarification"))
        self.assertFalse(first.citations)
        resumed = backend.ask("Original", clarification="Academic year 2026/27")
        self.assertEqual(resumed.status, "answered")
        self.assertIn("2026/27", retriever.calls[1][0])
        self.assertEqual(client.calls[1]["input"]["clarification"], "Academic year 2026/27")
        self.assertEqual(resumed.budget["used"]["retrieval_rounds"], 1)

    def test_abstention_has_no_fake_citations(self):
        result = self.run_backend(client=Client(final("abstain")))
        self.assertEqual((result.status, result.stop_reason), ("abstained", "insufficient_evidence"))
        self.assertFalse(result.citations)
        self.assertFalse(result.sources)

    def test_empty_initial_search_can_be_rewritten(self):
        result = self.run_backend(Retriever([], [hit()]), Client(retrieve(), final()))
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.retrieval_rounds[0]["hits"], [])

    def test_answer_with_empty_context_is_rejected(self):
        result = self.run_backend(Retriever([]), Client(final()))
        self.assertEqual(result.status, "invalid_response")
        self.assertEqual(result.answer, "")

    def test_repeated_query_stops_without_another_search(self):
        retriever, client = Retriever(), Client(retrieve("  ORIGINAL   QUESTION "))
        result = self.run_backend(retriever, client)
        self.assertEqual(result.stop_reason, "repeated_query")
        self.assertEqual(len(retriever.calls), 1)
        self.assertEqual(len(client.calls), 1)

    def test_aliases_cannot_bypass_repeated_query_check(self):
        retriever, client = Retriever(), Client(retrieve("Original", "学费与缴费"))
        result = AgenticRAGBackend(retriever, client).ask("Original", topic="fees")
        self.assertEqual(result.stop_reason, "repeated_query")
        self.assertEqual(len(retriever.calls), 1)

    def test_no_new_evidence_stops_without_extra_model_call(self):
        for second in ([hit()], []):
            with self.subTest(second=second):
                retriever, client = Retriever([hit()], second), Client(retrieve())
                result = self.run_backend(retriever, client)
                self.assertEqual(result.stop_reason, "no_new_evidence")
                self.assertEqual((len(retriever.calls), len(client.calls)), (2, 1))
                self.assertEqual(result.answer.count("[S"), 0)

    def test_retrieval_budget_stops_before_extra_tool(self):
        retriever, client = Retriever(), Client(retrieve())
        result = self.run_backend(retriever, client, budget=AgentBudget(max_retrieval_rounds=1))
        self.assertEqual(result.stop_reason, "retrieval_budget")
        self.assertEqual(len(retriever.calls), 1)

    def test_llm_budget_stops_before_wasted_retrieval(self):
        retriever, client = Retriever(), Client(retrieve())
        result = self.run_backend(retriever, client, budget=AgentBudget(max_llm_calls=1))
        self.assertEqual(result.stop_reason, "llm_budget")
        self.assertEqual((len(retriever.calls), len(client.calls)), (1, 1))

    def test_context_budget_preserves_chunks_without_truncation(self):
        client = Client(retrieve())
        result = self.run_backend(Retriever([hit()], [hit(2, "x" * 100)]), client,
                                  budget=AgentBudget(max_context_chars=100))
        self.assertEqual(result.status, "context_limit")
        self.assertEqual(result.retrieval_rounds[1]["hits"][0]["text"], "x" * 100)
        self.assertEqual(len(client.calls), 1)

    def test_time_budget_drops_late_answer(self):
        clock = Clock()
        client = Client(callback=lambda: setattr(clock, "now", 10))
        result = self.run_backend(client=client, budget=AgentBudget(max_elapsed_s=5), clock=clock)
        self.assertEqual((result.status, result.stop_reason), ("abstained", "time_budget"))
        self.assertFalse(result.citations)
        self.assertNotIn("Synthetic fixture statement", result.answer)

    def test_time_budget_after_retrieval_prevents_model_call(self):
        clock, client, retriever = Clock(), Client(), Retriever()
        original = retriever.search

        def slow_search(*args, **kwargs):
            clock.now = 10
            return original(*args, **kwargs)

        with patch.object(retriever, "search", side_effect=slow_search):
            result = self.run_backend(retriever, client, budget=AgentBudget(max_elapsed_s=5), clock=clock)
        self.assertEqual(result.stop_reason, "time_budget")
        self.assertFalse(client.calls)

    def test_usage_is_per_call_summed_and_timeout_is_remaining_budget(self):
        class MeteredClient(Client):
            def chat_with_metadata(self, messages, *, timeout_s):
                self.timeout = timeout_s
                return self.chat(messages), dict(prompt_tokens=10, completion_tokens=2, total_tokens=12)

        client = MeteredClient(retrieve(), final())
        result = self.run_backend(Retriever([hit()], [hit(2)]), client, clock=Clock())
        self.assertEqual(result.usage, dict(prompt_tokens=30, completion_tokens=6, total_tokens=36))
        self.assertEqual(client.timeout, 90)
        self.assertEqual([c["usage"]["total_tokens"] for c in result.tool_calls
                          if c["name"] == "agent_decision"], [12, 12])

    def test_partial_usage_is_null_not_an_estimate(self):
        class PartialClient(Client):
            def chat_with_metadata(self, messages, **kwargs):
                response = self.chat(messages)
                return response, None if len(self.calls) == 2 else dict(prompt_tokens=1, completion_tokens=1, total_tokens=2)

        result = self.run_backend(Retriever([hit()], [hit(2)]), PartialClient(retrieve(), final()))
        self.assertIsNone(result.usage)

    def test_partial_answer_is_not_published_when_an_original_requirement_is_missing(self):
        review = {"verdict": "incomplete", "requirements": [
            {"request": "First requested fact", "covered": True},
            {"request": "Second requested fact", "covered": False}],
            "unsupported_statements": [], "missing_information": ["Second requested fact"],
            "reason": "The draft silently omits the second part."}
        client = Client(review=review)
        result = self.run_backend(client=client)
        self.assertEqual((result.status, result.stop_reason), ("abstained", "answer_incomplete"))
        self.assertNotIn("Synthetic fixture statement", result.answer)
        self.assertFalse(result.citations)
        self.assertFalse(result.sources)
        self.assertEqual(client.calls[-1]["input"]["query"], "Original question")
        self.assertNotIn("previous_decisions", client.calls[-1])

    def test_unsupported_answer_is_not_published(self):
        review = {"verdict": "unsupported", "requirements": [{"request": "Requested fact", "covered": False}],
                  "unsupported_statements": [1], "missing_information": ["Support for the requested fact"],
                  "reason": "The cited fixture does not support the statement."}
        result = self.run_backend(client=Client(review=review))
        self.assertEqual(result.stop_reason, "answer_unsupported")
        self.assertFalse(result.citations)

    def test_review_cannot_exceed_shared_model_budget(self):
        client = Client()
        result = self.run_backend(client=client, budget=AgentBudget(max_llm_calls=1))
        self.assertEqual(result.stop_reason, "llm_budget")
        self.assertEqual(len(client.calls), 1)
        self.assertFalse(result.citations)
        self.assertNotIn("Synthetic fixture statement", result.answer)

    def test_malformed_or_failed_review_never_publishes_the_draft(self):
        malformed = [{}, {"verdict": "accept", "requirements": [{"request": "Missing part", "covered": False}],
                          "unsupported_statements": [], "missing_information": [], "reason": "Contradiction"},
                     {"verdict": "incomplete", "requirements": [{"request": "Missing part", "covered": False}],
                      "unsupported_statements": [], "missing_information": ["See https://invalid.example"], "reason": "URL injection"}]
        for review in malformed:
            with self.subTest(review=review):
                result = self.run_backend(client=Client(review=review))
                self.assertEqual(result.status, "invalid_response")
                self.assertEqual(result.answer, "")
        result = self.run_backend(client=Client(review=RuntimeError("private-provider-details")))
        self.assertEqual(result.status, "generation_error")
        self.assertEqual(result.answer, "")
        self.assertNotIn("private-provider-details", json.dumps(result.to_dict()))

    def test_late_review_cannot_publish_the_answer(self):
        clock = Clock()
        client = Client()
        def callback():
            if client.calls[-1].get("task") == "review_answer":
                clock.now = 10
        client.callback = callback
        result = self.run_backend(client=client, clock=clock, budget=AgentBudget(max_elapsed_s=5))
        self.assertEqual(result.stop_reason, "time_budget")
        self.assertFalse(result.citations)
        self.assertNotIn("Synthetic fixture statement", result.answer)

    def test_malformed_actions_and_citations_fail_closed(self):
        malformed = [None, [], {}, {**retrieve(), "topic": []},
                     {**retrieve(), "missing_information": []},
                     {**final(), "response": final("clarify")["response"]},
                     final(ids=["S99"]), {**final(), "extra": "unexpected"}]
        bad_link = final()
        bad_link["response"]["statements"][0]["text"] = "Go to https://evil.invalid/"
        malformed.append(bad_link)
        for response in malformed:
            with self.subTest(response=response):
                result = self.run_backend(client=Client(response))
                self.assertEqual(result.status, "invalid_response")
                self.assertFalse(result.answer)
                self.assertFalse(result.citations)

    def test_unknown_topic_is_rejected_before_second_tool_call(self):
        retriever = Retriever()
        result = self.run_backend(retriever, Client(retrieve(topic="unknown")))
        self.assertEqual(result.status, "invalid_response")
        self.assertEqual(len(retriever.calls), 1)

    def test_changed_chunk_identity_is_rejected(self):
        result = self.run_backend(Retriever([hit()], [replace(hit(), text="Changed text")]), Client(retrieve()))
        self.assertEqual(result.status, "source_mismatch")
        self.assertFalse(result.citations)

    def test_errors_are_sanitized_and_not_hidden_as_abstention(self):
        for retriever, client, status in [
            (Retriever(RuntimeError("private-token")), Client(), "retrieval_error"),
            (Retriever(), Client(RuntimeError("private-token")), "generation_error"),
            (Retriever([hit()], RuntimeError("private-token")), Client(retrieve()), "retrieval_error")]:
            result = self.run_backend(retriever, client)
            self.assertEqual(result.status, status)
            self.assertNotIn("private-token", json.dumps(result.to_dict()))
            self.assertFalse(result.answer)

    def test_invalid_input_calls_no_tools(self):
        for question, kwargs in [("", {}), (None, {}), ("q", {"persona": []}),
                                 ("q", {"persona": {"x": float("nan")}}),
                                 ("q", {"clarification": " "}), ("q", {"topic": []}),
                                 ("q", {"case_id": object()}), ("q", {"mode": "web"})]:
            with self.subTest(kwargs=kwargs):
                retriever, client = Retriever(), Client()
                result = AgenticRAGBackend(retriever, client).ask(question, **kwargs)
                self.assertEqual(result.status, "invalid_input")
                self.assertFalse(retriever.calls)
                self.assertFalse(client.calls)
                json.dumps(result.to_dict(), allow_nan=False)

    def test_invalid_budget_is_rejected(self):
        for kwargs in ({"max_llm_calls": 0}, {"max_retrieval_rounds": True},
                       {"max_context_chars": -1}, {"max_elapsed_s": float("nan")},
                       {"max_elapsed_s": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AgentBudget(**kwargs)

    def test_database_checks_every_round_and_rechecks_before_publication(self):
        from src.local_sources import LocalSourceError
        client = Client(retrieve(), final())
        with patch("src.local_sources.validate_hits", side_effect=["a" * 64, "a" * 64,
                     LocalSourceError("stale_evidence", "A document changed.")]) as check:
            result = self.run_backend(Retriever([hit()], [hit(2)]), client, db_path="fixture.db")
        self.assertEqual(check.call_count, 3)
        self.assertEqual(result.status, "stale_evidence")
        self.assertFalse(result.citations)
        self.assertEqual(result.answer, "")

    def test_database_identity_cannot_change_between_rounds(self):
        for next_sha in ("b" * 64, None):
            with self.subTest(next_sha=next_sha), \
                 patch("src.local_sources.validate_hits", side_effect=["a" * 64, next_sha]):
                result = self.run_backend(Retriever([hit()], [hit(2)]), Client(retrieve()), db_path="fixture.db")
            self.assertEqual(result.status, "source_mismatch")

    def test_real_sqlite_guard_rejects_document_invalidated_during_generation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "runtime.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE documents(url TEXT, active INTEGER, index_dirty INTEGER, corpus_sha256 TEXT)")
                conn.execute("INSERT INTO documents VALUES (?,1,0,?)", (hit().url, "a" * 64))

            def invalidate():
                with sqlite3.connect(db) as conn:
                    conn.execute("UPDATE documents SET index_dirty=1")

            result = self.run_backend(client=Client(callback=invalidate), db_path=db)
            self.assertEqual(result.status, "stale_evidence")
            self.assertFalse(result.citations)


if __name__ == "__main__":
    unittest.main()
