"""联网搜索功能（src/websearch.py + src/agent.py）的离线 eval，不联网。

评估项：
1. Bing 结果页解析（固定 HTML fixture，防页面结构回归）
2. fake 搜索适配器行为
3. web_search 工具 schema 符合 DeepSeek function 格式
4. agent 循环：模型发起搜索 -> 本地执行 -> 回灌 -> 产出最终回答 + 来源
5. 未知工具 / 非法参数不炸，错误回灌给模型
6. 超过轮数上限时收尾（不再发工具，直接要最终回答）

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import unittest

from src.agent import WEB_SEARCH_TOOL, WebSearchAgent
from src.websearch import (FakeSearchAdapter, SearchResult, build_searcher,
                           parse_bing_html)

BING_FIXTURE = """
<html><body><ol id="b_results">
<li class="b_algo">
  <h2><a href="https://www.cityu.edu.hk/admo/faq">FAQ | CityUHK Admission</a></h2>
  <div class="b_caption"><p>Admissions FAQ for non-local applicants to CityUHK.</p></div>
</li>
<li class="b_algo">
  <h2><a href="https://www.cityu.edu.hk/fo/htm/degree_fees.htm">Tuition Fees</a></h2>
  <div class="b_caption"><p>Fee schedule for government-funded programmes.</p></div>
</li>
<li class="b_algo"><h2>No anchor here</h2></li>
</ol></body></html>
"""


class FakeLLMClient:
    """按脚本返回 canned message；记录每次调用收到的 messages/tools。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self.script:
            return {"role": "assistant", "content": "（脚本耗尽）"}
        return self.script.pop(0)


def tool_call_msg(query: str, call_id: str = "call_1"):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": call_id,
            "type": "function",
            "function": {"name": "web_search",
                         "arguments": json.dumps({"query": query})},
        }],
    }


class TestWebSearchParsing(unittest.TestCase):
    def test_01_parse_bing_html(self):
        results = parse_bing_html(BING_FIXTURE, max_results=5)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "FAQ | CityUHK Admission")
        self.assertEqual(results[0].url, "https://www.cityu.edu.hk/admo/faq")
        self.assertIn("non-local", results[0].snippet)
        self.assertTrue(all(r.title and r.url for r in results))

    def test_02_parse_bing_html_respects_max_results(self):
        self.assertEqual(len(parse_bing_html(BING_FIXTURE, max_results=1)), 1)

    def test_03_fake_searcher_records_queries(self):
        searcher = FakeSearchAdapter()
        results = searcher.search("cityu 学费", max_results=3)
        self.assertEqual(searcher.queries, ["cityu 学费"])
        self.assertEqual(len(results), 1)

    def test_04_build_searcher_rejects_unknown(self):
        from src.websearch import SearchError
        with self.assertRaises(SearchError):
            build_searcher({"provider": "not-a-engine"})
        self.assertEqual(build_searcher({"provider": "fake"}).name, "fake")


class TestAgentLoop(unittest.TestCase):
    def test_05_tool_schema_matches_deepseek_function_format(self):
        self.assertEqual(WEB_SEARCH_TOOL["type"], "function")
        func = WEB_SEARCH_TOOL["function"]
        self.assertEqual(func["name"], "web_search")
        self.assertEqual(func["parameters"]["type"], "object")
        self.assertIn("query", func["parameters"]["required"])

    def test_06_agent_searches_then_answers(self):
        client = FakeLLMClient([
            tool_call_msg("CityU non-local visa"),
            {"role": "assistant", "content": "签证流程如下……[来源](https://example.com/fake)"},
        ])
        searcher = FakeSearchAdapter()
        agent = WebSearchAgent(client, searcher)
        result = agent.ask("非本地生怎么办学生签证？")

        self.assertIn("签证流程", result.answer)
        self.assertEqual(result.rounds, 2)
        self.assertEqual(result.queries, ["CityU non-local visa"])
        self.assertEqual(result.sources, ["https://example.com/fake"])
        # 第二轮调用应包含回灌的 tool 消息（搜索结果 JSON）
        second_messages = client.calls[1]["messages"]
        tool_msgs = [m for m in second_messages if m.get("role") == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        self.assertEqual(tool_msgs[0]["tool_call_id"], "call_1")
        self.assertIn("example.com/fake", tool_msgs[0]["content"])

    def test_07_unknown_tool_feeds_error_back(self):
        bad_call = {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "c9", "type": "function",
                            "function": {"name": "hack", "arguments": "{}"}}],
        }
        client = FakeLLMClient([
            bad_call,
            {"role": "assistant", "content": "好吧我直接回答"},
        ])
        result = WebSearchAgent(client, FakeSearchAdapter()).ask("hi")
        self.assertEqual(result.answer, "好吧我直接回答")
        tool_msgs = [m for m in client.calls[1]["messages"] if m.get("role") == "tool"]
        self.assertIn("unknown tool", tool_msgs[0]["content"])
        self.assertEqual(result.queries, [])   # 未执行任何搜索

    def test_08_max_rounds_fallback(self):
        client = FakeLLMClient([
            tool_call_msg("q1"),
            tool_call_msg("q2", call_id="call_2"),
            {"role": "assistant", "content": "收尾回答"},
        ])
        agent = WebSearchAgent(client, FakeSearchAdapter(), max_rounds=2)
        result = agent.ask("test")
        self.assertEqual(result.answer, "收尾回答")
        self.assertEqual(result.queries, ["q1", "q2"])
        # 最后一次调用不得携带工具（强制收尾）
        self.assertFalse(client.calls[-1]["tools"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
