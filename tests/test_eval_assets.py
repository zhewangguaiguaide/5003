import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_eval_assets import AssetError, ROOT, export_inputs, validate_bundle


class TestEvalAssets(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".test-tmp"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.corpus = self.root / "corpus.jsonl"
        document = dict(url="https://example.invalid/unit", title="Unit fixture", source="unit test",
                        content="Alpha prerequisite. Beta action.", date="", crawled_at="",
                        academic_year="", topic="", column="", error="", image_urls=[], file_urls=[])
        self.corpus.write_text(json.dumps(document) + "\n", encoding="utf-8")
        self.cases = self.root / "cases.jsonl"
        common = dict(split="dev", synthetic=True, review_status="synthetic_ready", persona={},
                      as_of="2026-10-26", corpus_sha256=hashlib.sha256(self.corpus.read_bytes()).hexdigest(),
                      gold_version="unit-v1", human_reviewed=False, reviewer_roles=[], forbidden_claims=[])
        self.rows = [dict(common, id="UNIT-1", query="What are the prerequisite and action?",
                          answerability="answerable", expected_action="answer", retrieval_applicable=True,
                          required_clarifications=[], required_facts=[
                              dict(id="f1", text="Alpha prerequisite.", critical=True),
                              dict(id="f2", text="Beta action.", critical=False)],
                          gold_evidence=[
                              dict(id="e1", doc_id=document["url"], locator="sentence 1",
                                   quote="Alpha prerequisite.", fact_ids=["f1"]),
                              dict(id="e2", doc_id=document["url"], locator="sentence 2",
                                   quote="Beta action.", fact_ids=["f2"])],
                          sufficient_evidence_sets=[["e1", "e2"]]),
                     dict(common, id="UNIT-2", query="Which action?", answerability="clarify",
                          expected_action="clarify", retrieval_applicable=False,
                          required_clarifications=["context"], required_facts=[], gold_evidence=[],
                          sufficient_evidence_sets=[]),
                     dict(common, id="UNIT-3", query="What is my private status?", answerability="unanswerable",
                          expected_action="refer", retrieval_applicable=False, required_clarifications=[],
                          required_facts=[], gold_evidence=[], sufficient_evidence_sets=[])]
        self.rubric = ROOT / "evals/rubric.json"
        self.save()

    def save(self):
        self.cases.write_text("".join(json.dumps(row) + "\n" for row in self.rows), encoding="utf-8")

    def validate(self, **kwargs):
        return validate_bundle(self.corpus, self.cases, self.rubric, **kwargs)

    def test_case_contract_is_bound_to_actual_bytes(self):
        summary = self.validate()
        self.assertEqual((summary["documents"], summary["cases"], summary["answerable"]), (1, 3, 1))
        self.assertEqual(summary["corpus_sha256"], hashlib.sha256(self.corpus.read_bytes()).hexdigest())

    def test_changed_snapshot_cannot_reuse_gold(self):
        self.corpus.write_bytes(self.corpus.read_bytes() + b"\n")
        with self.assertRaisesRegex(AssetError, "SHA256 mismatch"):
            self.validate()

    def test_fabricated_quote_rejected(self):
        self.rows[0]["gold_evidence"][0]["quote"] = "This quotation does not exist."
        self.save()
        with self.assertRaisesRegex(AssetError, "quote absent"):
            self.validate()

    def test_broken_fact_and_evidence_references_rejected(self):
        for field in ("fact_ids", "sufficient_evidence_sets"):
            with self.subTest(field=field):
                original = json.loads(json.dumps(self.rows[0]))
                if field == "fact_ids":
                    self.rows[0]["gold_evidence"][0][field] = ["missing"]
                else:
                    self.rows[0][field] = [["missing"]]
                self.save()
                with self.assertRaisesRegex(AssetError, "reference"):
                    self.validate()
                self.rows[0] = original

    def test_incomplete_sufficient_evidence_rejected(self):
        self.rows[0]["sufficient_evidence_sets"] = [["e1"]]
        self.save()
        with self.assertRaisesRegex(AssetError, "misses required facts"):
            self.validate()

    def test_synthetic_dev_is_not_frozen_gold(self):
        with self.assertRaisesRegex(AssetError, "frozen requires real TEST"):
            self.validate(require_frozen=True)
        with self.assertRaisesRegex(AssetError, "not enough"):
            self.validate(min_answerable=20)

    def test_export_contains_inputs_only_even_with_extra_gold_fields(self):
        self.rows[0]["private_annotation"] = "must never reach the model"
        self.save()
        destination = self.root / "runs" / "inputs.jsonl"
        export_inputs(self.cases, destination, root=self.root)
        exported = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(exported), 3)
        for row in exported:
            self.assertEqual(set(row), {"case_id", "input"})
            self.assertEqual(set(row["input"]), {"query", "persona", "as_of"})
        self.assertNotIn("private_annotation", destination.read_text(encoding="utf-8"))

    def test_export_rejects_outside_path_and_existing_file(self):
        with self.assertRaisesRegex(AssetError, "inside repository runs"):
            export_inputs(self.cases, self.root / "outside.jsonl", root=self.root)
        destination = self.root / "runs" / "inputs.jsonl"
        export_inputs(self.cases, destination, root=self.root)
        with self.assertRaisesRegex(AssetError, "overwrite"):
            export_inputs(self.cases, destination, root=self.root)


if __name__ == "__main__":
    unittest.main()
