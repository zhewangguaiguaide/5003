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

    def test_reachable_cycle_without_exit_rejected(self):
        flow = self.catalog["workflows"][0]
        flow["nodes"].extend([
            dict(id="loop1", label="pending", kind="context", rule_ids=[]),
            dict(id="loop2", label="pending", kind="context", rule_ids=[]),
        ])
        flow["edges"].extend([
            dict(source=flow["nodes"][0]["id"], target="loop1", condition="pending"),
            dict(source="loop1", target="loop2", condition=""),
            dict(source="loop2", target="loop1", condition=""),
        ])
        with self.assertRaisesRegex(PolicyError, "cannot reach an end"):
            validate_catalog(self.catalog)

    def test_payment_scope_and_evidence_cannot_be_dropped(self):
        for field, value in (("charging_basis", "all"), ("statement_number", 1),
                             ("due_date", "2029-01-01"), ("rule_ids", []),
                             ("source_ids", ["S11"])):
            with self.subTest(field=field):
                catalog = copy.deepcopy(self.catalog)
                catalog["payment_schedule"][0][field] = value
                with self.assertRaises((PolicyError, ValueError)):
                    validate_catalog(catalog)

    def test_handoff_cannot_drop_owner_or_reference_missing_rule(self):
        for field, value in (("owner_roles", []), ("rule_ids", ["missing"])):
            with self.subTest(field=field):
                catalog = copy.deepcopy(self.catalog)
                catalog["open_items"][0][field] = value
                with self.assertRaisesRegex(PolicyError, "missing owner or dangling"):
                    validate_catalog(catalog)


if __name__ == "__main__":
    unittest.main()
