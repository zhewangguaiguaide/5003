"""N5 CLI isolation, diagnostics, and JSON interface (no real model/network)."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.main import main


class TestLocalCLI(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(list(args))
        return code, json.loads(out.getvalue())

    def test_demo_json_needs_no_config_storage_model_or_network(self):
        with patch("src.main.cfg.load_config", side_effect=AssertionError("config read")), \
             patch("src.main.SQLiteStorage", side_effect=AssertionError("storage opened")), \
             patch("src.llm.DeepSeekClient", side_effect=AssertionError("real model client")), \
             patch("src.local_sources.load_retriever", side_effect=AssertionError("real index")), \
             patch("socket.socket", side_effect=AssertionError("network opened")):
            code, payload = self.run_cli("--ask-local", "Show the demo evidence", "--rag-demo", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "answered")
        self.assertEqual(payload["mode"], "rag")
        self.assertIn("synthetic", payload["answer"].lower())
        self.assertEqual(payload["citations"][0]["url"], "https://example.invalid/n5-demo")
        self.assertTrue(any("synthetic" in x.lower() for x in payload["warnings"]))

    def test_missing_index_is_json_error_and_does_not_create_database(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("src.main.cfg.load_config", return_value={}), \
             patch("src.main.SQLiteStorage", side_effect=AssertionError("storage opened")):
            missing = Path(tmp) / "missing-index"
            db = Path(tmp) / "must-not-exist.db"
            code, payload = self.run_cli("--ask-local", "How do I pay?", "--index-dir", str(missing),
                                         "--db", str(db), "--json")
            self.assertFalse(db.exists())
            self.assertFalse(missing.exists())
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "index_unavailable")
        self.assertEqual(payload["answer"], "")
        self.assertTrue(payload["error"]["message"])

    def test_invalid_configuration_is_sanitized_json(self):
        with patch("src.main.cfg.load_config", side_effect=ValueError("secret-token")):
            code, payload = self.run_cli("--ask-local", "Question", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "config_error")
        self.assertNotIn("secret-token", json.dumps(payload))

    def test_invalid_modes_rejected_before_loading_or_mutating(self):
        invalid = [
            ["--ask", "Web", "--ask-local", "Local"],
            ["--rag-demo"], ["--json"], ["--topic", "fees"],
            ["--index-dir", "custom"],
            ["--ask-local", "Local", "--import-corpus", "private.jsonl"],
            ["--ask-local", "Local", "--export", "private.jsonl"],
            ["--ask-local", "Local", "--migrate"],
            ["--ask-local", "Local", "--live"],
            ["--ask-local", "Local", "--mode", "fake"],
            ["--ask-local", "Local", "--dry-run"],
            ["--ask-local", "Local", "--rag-demo", "--db", "real.db"],
        ]
        with patch("src.main.cfg.load_config", side_effect=AssertionError("configuration read")), \
             patch("src.main.SQLiteStorage", side_effect=AssertionError("storage opened")):
            for argv in invalid:
                with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        main(argv)
                    self.assertEqual(error.exception.code, 2)

    def test_existing_web_entry_still_dispatches_to_web_agent(self):
        with patch("src.main.cfg.load_config", return_value={}), \
             patch("src.main.cmd_ask", return_value=0) as web, \
             patch("src.main.cmd_ask_local", side_effect=AssertionError("local called")):
            self.assertEqual(main(["--ask", "Web question"]), 0)
        web.assert_called_once_with({}, "Web question")


if __name__ == "__main__":
    unittest.main()
