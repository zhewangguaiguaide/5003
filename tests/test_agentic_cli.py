"""N7 command-line isolation, budget validation and structured output."""
from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from src.main import main


class TestAgenticCLI(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(list(args))
        return code, json.loads(out.getvalue())

    def test_demo_two_rounds_needs_no_config_model_database_or_network(self):
        with patch("src.main.cfg.load_config", side_effect=AssertionError("config")), \
             patch("src.main.SQLiteStorage", side_effect=AssertionError("storage")), \
             patch("src.local_sources.load_retriever", side_effect=AssertionError("model")), \
             patch("socket.socket", side_effect=AssertionError("network")):
            code, result = self.run_cli("--ask-local", "Show synthetic fixtures", "--local-mode", "agentic_rag",
                                        "--rag-demo", "--json", "--persona", '{"programme":"TPG"}',
                                        "--as-of", "2026-11-18", "--clarification", "Development fixtures only")
        self.assertEqual((code, result["status"], result["mode"]), (0, "answered", "agentic_rag"))
        self.assertEqual(len(result["retrieval_rounds"]), 2)
        self.assertEqual(len(result["citations"]), 2)
        self.assertEqual(result["stop_reason"], "evidence_sufficient")

    def test_cli_budget_stops_without_forcing_answer(self):
        code, result = self.run_cli("--ask-local", "Show synthetic fixtures", "--local-mode", "agentic_rag",
                                    "--rag-demo", "--json", "--agent-max-rounds", "1")
        self.assertEqual((code, result["status"], result["stop_reason"]), (0, "abstained", "retrieval_budget"))
        self.assertEqual(len(result["retrieval_rounds"]), 1)
        self.assertFalse(result["citations"])

    def test_invalid_agent_options_rejected_before_loading(self):
        invalid = [["--local-mode", "agentic_rag"], ["--persona", "{}"],
                   ["--ask-local", "q", "--clarification", "year"],
                   ["--ask-local", "q", "--agent-max-rounds", "3"],
                   ["--ask-local", "q", "--local-mode", "agentic_rag", "--retrieve-only"],
                   ["--ask-local", "q", "--persona", "[]"],
                   ["--ask-local", "q", "--persona", '{"value":NaN}'],
                   ["--ask-local", "q", "--local-mode", "agentic_rag", "--agent-max-rounds", "0"],
                   ["--ask-local", "q", "--local-mode", "agentic_rag", "--agent-timeout-s", "nan"]]
        with patch("src.main.cfg.load_config", side_effect=AssertionError("config")):
            for argv in invalid:
                with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as exc:
                        main(argv)
                    self.assertEqual(exc.exception.code, 2)

    def test_missing_index_is_agentic_error_without_storage_creation(self):
        with patch("src.main.cfg.load_config", return_value={}), \
             patch("src.main.SQLiteStorage", side_effect=AssertionError("storage")):
            code, result = self.run_cli("--ask-local", "q", "--local-mode", "agentic_rag", "--json",
                                        "--index-dir", "does-not-exist-n7-fixture")
        self.assertEqual((code, result["status"], result["mode"]), (1, "index_unavailable", "agentic_rag"))


if __name__ == "__main__":
    unittest.main()
