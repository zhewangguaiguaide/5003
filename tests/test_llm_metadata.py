"""Provider-independent checks of backward compatibility and per-call limits."""
from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.llm import DeepSeekClient, LLMConfig, LLMError


class TestLLMMetadata(unittest.TestCase):
    def client(self):
        return DeepSeekClient(LLMConfig(api_key="synthetic-fixture-key"))

    def response(self, payload):
        post = Mock(return_value=SimpleNamespace(status_code=200, json=lambda: payload))
        return post, patch.dict(sys.modules, {"curl_cffi": SimpleNamespace(requests=SimpleNamespace(post=post))})

    def test_chat_remains_message_only_and_usage_is_per_call(self):
        message = {"role": "assistant", "content": "fixture"}
        usage = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
        _, patched = self.response({"choices": [{"message": message}], "usage": usage})
        client = self.client()
        with patched:
            self.assertEqual(client.chat([]), message)
            self.assertEqual(client.chat_with_metadata([]), (message, usage))

    def test_remaining_deadline_caps_provider_timeout(self):
        post, patched = self.response({"choices": [{"message": {"content": "fixture"}}]})
        with patched:
            self.client().chat_with_metadata([], timeout_s=2.5)
        self.assertEqual(post.call_args.kwargs["timeout"], 2.5)

    def test_larger_budget_does_not_increase_configured_timeout(self):
        post, patched = self.response({"choices": [{"message": {"content": "fixture"}}]})
        with patched:
            self.client().chat_with_metadata([], timeout_s=120)
        self.assertEqual(post.call_args.kwargs["timeout"], 60)

    def test_missing_usage_is_null(self):
        _, patched = self.response({"choices": [{"message": {"content": "fixture"}}]})
        with patched:
            self.assertIsNone(self.client().chat_with_metadata([])[1])

    def test_invalid_deadline_and_response_are_diagnostic(self):
        for timeout in (0, -1, True, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.client().chat_with_metadata([], timeout_s=timeout)
        _, patched = self.response({"choices": [{"message": None}]})
        with patched, self.assertRaises(LLMError):
            self.client().chat([])


if __name__ == "__main__":
    unittest.main()
