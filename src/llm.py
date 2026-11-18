"""DeepSeek LLM 客户端（OpenAI Chat Completions 兼容）。

官方事实核查（2026-09-26，api-docs.deepseek.com）：
- DeepSeek API **没有**服务端联网搜索；Responses API 里 `web_search` 等内置
  工具会被**静默忽略**（见官方 guides/responses_api 兼容性表）。
- 联网搜索的官方正解 = 客户端 function calling：模型产出 web_search 调用 ->
  本地执行搜索 -> 结果回灌（见 src/agent.py）。
- 模型名用 `deepseek-flash`；旧名 `deepseek-v4-flash` 已退役，仅作路由兼容。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class LLMError(RuntimeError):
    """LLM API 调用失败（含 HTTP 状态码与响应摘录）。"""


@dataclass
class LLMConfig:
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    api_key: str = ""                 # 一般不写配置里，走环境变量
    api_key_env: str = "DEEPSEEK_API_KEY"
    thinking: bool = False            # 工具调用演示默认关思考（省 token）
    temperature: float = 0.3
    max_tokens: int = 2048
    timeout_s: int = 60

    @classmethod
    def from_conf(cls, conf: Optional[Dict[str, Any]]) -> "LLMConfig":
        conf = conf or {}
        return cls(
            base_url=conf.get("base_url", cls.base_url),
            model=conf.get("model", cls.model),
            api_key=conf.get("api_key", ""),
            api_key_env=conf.get("api_key_env", cls.api_key_env),
            thinking=bool(conf.get("thinking", False)),
            temperature=float(conf.get("temperature", 0.3)),
            max_tokens=int(conf.get("max_tokens", 2048)),
            timeout_s=int(conf.get("timeout_s", 60)),
        )

    def resolved_key(self) -> str:
        return self.api_key or os.environ.get(self.api_key_env, "")


class DeepSeekClient:
    """最小 Chat Completions 客户端：chat(messages, tools) -> message dict。"""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def _payload(self, messages: List[Dict[str, Any]],
                 tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        cfg = self.config
        payload: Dict[str, Any] = {
            "model": cfg.model,
            "messages": messages,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "stream": False,
            # DeepSeek 默认 thinking=enabled；显式给出开关，行为可复现
            "thinking": {"type": "enabled" if cfg.thinking else "disabled"},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    def chat(self, messages: List[Dict[str, Any]],
             tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        message, _ = self.chat_with_metadata(messages, tools)
        return message

    def chat_with_metadata(self, messages: List[Dict[str, Any]],
                           tools: Optional[List[Dict[str, Any]]] = None, *,
                           timeout_s: float | None = None) -> tuple[Dict[str, Any], dict | None]:
        """Per-call usage and timeout; preserves chat()'s message-only contract."""
        import math
        timeout = self.config.timeout_s
        if timeout_s is not None:
            if (type(timeout_s) not in (int, float)
                    or not math.isfinite(timeout_s) or timeout_s <= 0):
                raise ValueError("timeout_s must be positive and finite")
            timeout = min(timeout, timeout_s)
        key = self.config.resolved_key()
        if not key:
            raise LLMError(
                f"缺少 API Key：请设置环境变量 {self.config.api_key_env}"
                "（或 config.yaml 的 llm.api_key）")
        from curl_cffi import requests  # 延迟导入：离线测试无需网络库

        url = self.config.base_url.rstrip("/") + "/chat/completions"
        try:
            resp = requests.post(
                url,
                json=self._payload(messages, tools),
                headers={"Authorization": f"Bearer {key}"},
                timeout=timeout,
            )
        except Exception as exc:
            raise LLMError(f"请求失败: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            message = data["choices"][0]["message"]
            if not isinstance(message, dict):
                raise TypeError("Invalid message")
            usage = data.get("usage")
            return message, usage if isinstance(usage, dict) else None
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"响应结构异常: {str(data)[:300]}") from exc
