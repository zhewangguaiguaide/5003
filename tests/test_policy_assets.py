import copy
import json
import unittest

from scripts.check_policy_assets import PolicyError, ROOT, render_views, validate_catalog


class TestPolicyAssets(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "knowledge/catalog.json").read_text(encoding="utf-8"))

    def test_candidates_remain_visible_as_candidates(self):
        result = validate_catalog(self.catalog)
        self.assertEqual(result["candidate_rules"], result["rules"])
        self.assertEqual(result["workflows"], 8)
        self.assertIn("```mermaid", render_views(self.catalog))

    def test_official_looking_external_domain_rejected(self):
        self.catalog["sources"][0]["url"] = "https://cityu.edu.hk.example.invalid/policy"
        with self.assertRaisesRegex(PolicyError, "official HTTPS"):
            validate_catalog(self.catalog)

    def test_broken_evidence_and_flow_references_rejected(self):
        for kind in ("source", "edge"):
            with self.subTest(kind=kind):
                catalog = copy.deepcopy(self.catalog)
                if kind == "source":
                    catalog["rules"][0]["source_ids"] = ["missing"]
                else:
                    catalog["workflows"][0]["edges"][0]["target"] = "missing"
                with self.assertRaises(PolicyError):
                    validate_catalog(catalog)

    def test_index_only_cannot_be_promoted_to_reviewed(self):
        rule = self.catalog["rules"][0]
        rule["review_status"] = "reviewed"
        rule["reviewer_roles"] = ["role2", "role6"]
        with self.assertRaisesRegex(PolicyError, "full source snapshot"):
            validate_catalog(self.catalog)

    def test_no_corpus_cannot_pass_ready_gate(self):
        with self.assertRaisesRegex(PolicyError, "accepted corpus file"):
            validate_catalog(self.catalog, require_ready=True)


if __name__ == "__main__":
    unittest.main()
