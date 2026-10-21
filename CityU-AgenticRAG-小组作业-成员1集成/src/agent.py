"""Web 搜索 Agent：DeepSeek function calling 循环（官方 tool_calls 标准模式）。

流程：
1. messages + tools=[web_search] 发给 DeepSeek；
2. 模型返回 tool_calls -> 本地执行搜索（src/websearch.py）-> tool 消息回灌；
3. 模型综合搜索结果产出最终回答（附来源 URL）。

这正是"给 ds 调用装联网搜索"的官方支持形态：DeepSeek API 无服务端搜索，
Responses API 的内置 web_search 被静默忽略（官方文档已核实）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .websearch import SearchError, SearchResult

WEB_SEARCH_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "搜索互联网获取最新信息。当问题涉及时效性、学校官网最新公告、"
            "或你不确定的事实时，调用本工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "搜索关键词，建议包含站点/主题，如 'CityU tuition fee'"},
            },
            "required": ["query"],
        },
    },
}

SYSTEM_PROMPT = (
    "你是香港城市大学（CityUHK）学生服务问答助手。"
    "回答规则：① 优先依据 web_search 工具返回的结果作答；"
    "② 答案用简体中文、要点式；③ 每个关键事实后标注来源 URL；"
    "④ 搜索结果没有覆盖的内容，明说'未查到'，不要编造。"
)


@dataclass
class AgentAnswer:
    answer: str
    sources: List[str] = field(default_factory=list)   # 本轮实际用到的来源 URL（去重）
    queries: List[str] = field(default_factory=list)   # 实际执行过的搜索词
    rounds: int = 0                                    # LLM 调用轮数


def _format_results(results: List[SearchResult]) -> str:
    """搜索结果序列化后回灌给模型。"""
    return json.dumps(
        [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results],
        ensure_ascii=False,
    )


class WebSearchAgent:
    """最小 agent 循环：模型要搜就搜，搜完回灌，直到模型给出最终回答。"""

    def __init__(self, client, searcher, max_rounds: int = 4,
                 max_results: int = 5, system_prompt: str = SYSTEM_PROMPT) -> None:
        self.client = client
        self.searcher = searcher
        self.max_rounds = max_rounds
        self.max_results = max_results
        self.system_prompt = system_prompt

    def _run_tool(self, call: Dict[str, Any], answer: AgentAnswer) -> str:
        func = (call.get("function") or {})
        if func.get("name") != "web_search":
            return f"error: unknown tool {func.get('name')!r}"
        try:
            args = json.loads(func.get("arguments") or "{}")
        except json.JSONDecodeError:
            return "error: 工具参数不是合法 JSON"
        query = str(args.get("query") or "").strip()
        if not query:
            return "error: query 为空"
        answer.queries.append(query)
        try:
            results = self.searcher.search(query, max_results=self.max_results)
        except SearchError as exc:
            return f"error: 搜索失败 {exc}"
        for r in results:
            if r.url not in answer.sources:
                answer.sources.append(r.url)
        return _format_results(results)

    def ask(self, question: str) -> AgentAnswer:
        answer = AgentAnswer(answer="")
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]
        for _ in range(self.max_rounds):
            answer.rounds += 1
            msg = self.client.chat(messages, tools=[WEB_SEARCH_TOOL])
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                answer.answer = msg.get("content") or ""
                return answer
            messages.append(msg)  # 原样回append（含 tool_calls），官方示例同款
            for call in tool_calls:
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": self._run_tool(call, answer),
                })
        # 超过轮数上限：不再给工具，要一个收尾回答
        answer.rounds += 1
        final = self.client.chat(messages + [
            {"role": "user", "content": "请基于已有搜索结果直接给出最终回答。"}])
        answer.answer = final.get("content") or ""
        return answer
