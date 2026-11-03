import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.evaluate_wsb import (
    AssetError,
    configure_model_path,
    configure_rerank_model,
    ensure_retrieval_cases,
    match_case,
    normalize_text,
    run_evaluation,
    summarize_results,
    write_results,
)


def hit(rank_text: str, *, doc_id: str = "https://example.test/doc", chunk_id: str = "c1"):
    return SimpleNamespace(
        chunk_id=chunk_id,
        doc_id=doc_id,
        url=doc_id,
        text=rank_text,
        title="Example",
        topic="registration",
        academic_year="2026-27",
        score=0.9,
    )


def case(*, facts=None, evidence=None, sets=None, case_id="CASE-1"):
    facts = facts or [
        {"id": "f1", "text": "The deadline is 15 October.", "critical": True},
        {"id": "f2", "text": "The fee is HK$500.", "critical": True},
    ]
    evidence = evidence or [
        {
            "id": "e1",
            "doc_id": "https://example.test/doc",
            "locator": "paragraph 1",
            "quote": "The deadline is 15 October.",
            "fact_ids": ["f1"],
        },
        {
            "id": "e2",
            "doc_id": "https://example.test/doc",
            "locator": "paragraph 2",
            "quote": "The fee is HK$500.",
            "fact_ids": ["f2"],
        },
    ]
    return {
        "id": case_id,
        "query": "What is the deadline and fee?",
        "answerability": "answerable",
        "retrieval_applicable": True,
        "required_facts": facts,
        "gold_evidence": evidence,
        "sufficient_evidence_sets": sets or [["e1", "e2"]],
    }


class MatchingTests(unittest.TestCase):
    def test_normalize_text_collapses_whitespace(self):
        self.assertEqual(normalize_text("  Alpha\n\t beta  "), "Alpha beta")

    def test_quote_matching_ignores_whitespace_differences(self):
        row = match_case(
            case(facts=[{"id": "f1", "text": "Deadline", "critical": True}],
                 evidence=[{"id": "e1", "doc_id": "https://example.test/doc",
                            "locator": "p1", "quote": "The deadline   is\n15 October.",
                            "fact_ids": ["f1"]}],
                 sets=[["e1"]]),
            [hit("Intro\nThe deadline is 15 October.\nMore")],
        )
        self.assertTrue(row["hit_at_1"])
        self.assertEqual(row["first_relevant_rank"], 1)

    def test_url_match_without_quote_is_not_a_hit(self):
        row = match_case(
            case(facts=[{"id": "f1", "text": "Deadline", "critical": True}],
                 evidence=[{"id": "e1", "doc_id": "https://example.test/doc",
                            "locator": "p1", "quote": "The deadline is 15 October.",
                            "fact_ids": ["f1"]}],
                 sets=[["e1"]]),
            [hit("This page mentions a different deadline.")],
        )
        self.assertFalse(row["hit_at_5"])
        self.assertIn("no_evidence_quote_in_top_k", row["failure_reasons"])

    def test_exact_quote_in_wrong_document_is_not_a_hit(self):
        row = match_case(
            case(facts=[{"id": "f1", "text": "Deadline", "critical": True}],
                 evidence=[{"id": "e1", "doc_id": "https://example.test/doc",
                            "locator": "p1", "quote": "The deadline is 15 October.",
                            "fact_ids": ["f1"]}],
                 sets=[["e1"]]),
            [hit("The deadline is 15 October.", doc_id="https://example.test/other")],
        )
        self.assertFalse(row["hit_at_5"])

    def test_partial_and_complete_evidence_are_distinguished(self):
        partial = match_case(case(), [hit("The deadline is 15 October.")])
        self.assertAlmostEqual(partial["fact_coverage"], 0.5)
        self.assertEqual(partial["critical_fact_coverage"], 0.5)
        self.assertFalse(partial["complete_evidence"])
        self.assertEqual(partial["missing_fact_ids"], ["f2"])

        complete = match_case(case(), [
            hit("The deadline is 15 October.", chunk_id="c1"),
            hit("The fee is HK$500.", chunk_id="c2"),
        ])
        self.assertEqual(complete["fact_coverage"], 1.0)
        self.assertTrue(complete["complete_evidence"])

    def test_first_relevant_rank_and_hit_at_five(self):
        unrelated = [hit(f"Unrelated {i}", chunk_id=f"u{i}") for i in range(4)]
        relevant = hit("The deadline is 15 October.", chunk_id="c5")
        row = match_case(
            case(facts=[{"id": "f1", "text": "Deadline", "critical": True}],
                 evidence=[{"id": "e1", "doc_id": "https://example.test/doc",
                            "locator": "p1", "quote": "The deadline is 15 October.",
                            "fact_ids": ["f1"]}],
                 sets=[["e1"]]),
            unrelated + [relevant],
        )
        self.assertFalse(row["hit_at_1"])
        self.assertTrue(row["hit_at_5"])
        self.assertEqual(row["first_relevant_rank"], 5)

    def test_top_k_limit_is_applied(self):
        row = match_case(
            case(facts=[{"id": "f1", "text": "Deadline", "critical": True}],
                 evidence=[{"id": "e1", "doc_id": "https://example.test/doc",
                            "locator": "p1", "quote": "The deadline is 15 October.",
                            "fact_ids": ["f1"]}],
                 sets=[["e1"]]),
            [hit("Unrelated"), hit("The deadline is 15 October.", chunk_id="c2")],
            k=1,
        )
        self.assertFalse(row["hit_at_5"])
        self.assertIsNone(row["first_relevant_rank"])


class RunEvaluationTests(unittest.TestCase):
    def test_candidate_depth_is_used_before_rerank(self):
        class FakeRetriever:
            def __init__(self):
                self.search_args = None
                self.rerank_hit_count = None

            def search(self, query, topic=None, k=5, rerank=False):
                self.search_args = (topic, k, rerank)
                return [hit("The deadline is 15 October.")]

            def rerank_hits(self, query, hits):
                self.rerank_hit_count = len(hits)
                return hits

        retriever = FakeRetriever()
        rows = run_evaluation(
            [case(facts=[{"id": "f1", "text": "Deadline", "critical": True}],
                  evidence=[{"id": "e1", "doc_id": "https://example.test/doc",
                             "locator": "p1", "quote": "The deadline is 15 October.",
                             "fact_ids": ["f1"]}],
                  sets=[["e1"]])],
            retriever,
            k=5,
            rerank=True,
            candidate_k=2,
        )
        self.assertEqual(retriever.search_args, (None, 5, False))
        self.assertEqual(retriever.rerank_hit_count, 1)
        self.assertTrue(rows[0]["hit_at_5"])


class SummaryTests(unittest.TestCase):
    def test_failed_cases_remain_in_denominator(self):
        good = match_case(
            case(case_id="GOOD", facts=[{"id": "f1", "text": "Deadline", "critical": True}],
                 evidence=[{"id": "e1", "doc_id": "https://example.test/doc",
                            "locator": "p1", "quote": "The deadline is 15 October.",
                            "fact_ids": ["f1"]}],
                 sets=[["e1"]]),
            [hit("The deadline is 15 October.")],
        )
        bad = match_case(case(case_id="BAD"), [hit("Nothing relevant")])
        summary = summarize_results([good, bad], "abc")
        self.assertEqual(summary["cases"], 2)
        self.assertEqual(summary["hit_at_5"]["count"], 1)
        self.assertEqual(summary["hit_at_5"]["rate"], 0.5)
        self.assertFalse(summary["semantic_answer_quality"])

    def test_empty_results_are_rejected(self):
        with self.assertRaisesRegex(AssetError, "no cases"):
            summarize_results([], "abc")


class ContractTests(unittest.TestCase):
    def test_non_retrieval_case_is_rejected(self):
        invalid = case()
        invalid["retrieval_applicable"] = False
        with self.assertRaisesRegex(AssetError, "retrieval-applicable"):
            ensure_retrieval_cases([invalid])

    def test_output_must_be_inside_repository_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(AssetError, "inside repository runs"):
                write_results([], {}, root / "outside.jsonl", root / "runs" / "summary.json", root=root)

    def test_existing_outputs_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "runs" / "case.jsonl"
            output.parent.mkdir(parents=True)
            output.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(AssetError, "overwrite"):
                write_results([], {}, output, root / "runs" / "summary.json", root=root)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep")

    def test_local_model_path_replaces_default_model_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = SimpleNamespace(model_name="default-model")
            configured = configure_model_path(fake, Path(tmp))
            self.assertEqual(configured.model_name, str(Path(tmp).resolve()))

    def test_local_rerank_model_path_replaces_default_model_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = SimpleNamespace(rerank_model_name="default-reranker")
            configured = configure_rerank_model(fake, Path(tmp))
            self.assertEqual(configured.rerank_model_name, str(Path(tmp).resolve()))

    def test_missing_local_model_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            with self.assertRaisesRegex(AssetError, "model path"):
                configure_model_path(SimpleNamespace(model_name="default-model"), missing)

    def test_write_results_creates_jsonl_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "runs" / "case.jsonl"
            summary_path = root / "runs" / "summary.json"
            row = {"case_id": "C1", "hit_at_5": True}
            summary = {"cases": 1, "hit_at_5": {"rate": 1.0}}
            write_results([row], summary, output, summary_path, root=root)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), row)
            self.assertEqual(json.loads(summary_path.read_text(encoding="utf-8")), summary)


if __name__ == "__main__":
    unittest.main()
