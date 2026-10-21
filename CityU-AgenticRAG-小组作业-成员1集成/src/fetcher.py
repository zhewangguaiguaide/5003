"""抓取层：限速 + 重试 + WAF 挑战页检测 + 可替换适配器。

关键实测结论（见 docs/可行性研究.md 第 1、3 节）：
1. cityu.edu.hk 全站在 Imperva Incapsula 之后，纯 HTTP（curl/requests/scrapling
   Fetcher/curl_cffi TLS 伪装）全部被拦，返回 HTTP 200 的挑战页——状态码不可信。
2. scrapling StealthyFetcher（patchright 无头 Chromium）实测可拿到真实正文。
3. 慢加载页面必须 disable_resources=True，否则 network_idle/goto 会一直超时。
4. 正常页面 HTML 里也会出现 `_Incapsula_Resource`（WAF 注入脚本），
   因此挑战页判定必须"标记 + 内容极短"两个条件同时成立。
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

CHALLENGE_MARKERS = ("_Incapsula_Resource", "incident_id", "visid_incap_", "Incapsula")
CHALLENGE_MAX_LEN = 20000  # 挑战页约 850B；正常内容页远超此值


class FetchError(RuntimeError):
    """抓取失败（网络错误、404、WAF 挑战未通过）。"""


def looks_like_challenge(html: str) -> bool:
    """判断是否为 WAF 拦截页（假 200）。"""
    if not html:
        return True
    if len(html) > CHALLENGE_MAX_LEN:
        return False
    return any(marker in html for marker in CHALLENGE_MARKERS)


class ScraplingStealthyAdapter:
    """无头浏览器适配器（默认，实测可过 Incapsula）。"""

    name = "stealthy"

    def __init__(self, headless: bool = True, disable_resources: bool = True,
                 timeout_ms: int = 30000) -> None:
        from scrapling.fetchers import StealthyFetcher  # 延迟导入：测试环境无需安装

        self._fetcher = StealthyFetcher
        self._options = dict(
            headless=headless,
            network_idle=False,
            disable_resources=disable_resources,  # 关键：否则部分页面 goto 永远超时
            timeout=timeout_ms,
        )

    def fetch(self, url: str) -> str:
        page = self._fetcher.fetch(url, **self._options)
        if page.status >= 400:
            raise FetchError(f"HTTP {page.status}: {url}")
        return getattr(page, "html_content", None) or str(page)


class ScraplingHttpAdapter:
    """纯 HTTP 适配器：仅适用于不在 WAF 后的站点（如 libguides）。"""

    name = "http"

    def __init__(self, timeout_s: int = 10) -> None:
        from scrapling.fetchers import Fetcher

        self._fetcher = Fetcher
        self._timeout = timeout_s

    def fetch(self, url: str) -> str:
        page = self._fetcher.get(url, timeout=self._timeout)
        final_url = str(getattr(page, 'url', url)).lower()
        if any(marker in final_url for marker in ('auth.cityu.edu.hk', '/sso/', '/login', '/signin')):
            raise FetchError(f"redirect to authentication: {url}")
        if page.status >= 400:
            raise FetchError(f"HTTP {page.status}: {url}")
        return getattr(page, "html_content", None) or str(page)


class FakeFetcher:
    """离线测试适配器：pages 映射之外的 URL 视为 404。"""

    name = "fake"

    def __init__(self, pages: Dict[str, str]) -> None:
        self.pages = pages
        self.calls: List[str] = []

    def fetch(self, url: str) -> str:
        self.calls.append(url)
        if url not in self.pages:
            raise FetchError(f"404 {url}")
        return self.pages[url]


@dataclass
class FetchStats:
    requests: int = 0
    challenges: int = 0
    failures: int = 0
    errors: List[str] = field(default_factory=list)


class RateLimitedFetcher:
    """给任意适配器套上"礼貌"策略：随机延迟、重试、挑战页检测。"""

    def __init__(self, adapter, min_delay: float = 2.0, max_delay: float = 3.0,
                 max_retries: int = 2, sleep: Callable[[float], None] = time.sleep,
                 rng: Optional[random.Random] = None) -> None:
        self.adapter = adapter
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self._sleep = sleep
        self._rng = rng or random.Random(20260925)
        self.stats = FetchStats()
        self._first_call_done = False

    def fetch(self, url: str) -> str:
        last_error = ""
        for attempt in range(self.max_retries + 1):
            if self._first_call_done:  # 首次请求不等待
                self._rng.uniform  # noqa: B018 - 保持接口可读性
                self._sleep(self._rng.uniform(self.min_delay, self.max_delay))
            else:
                self._first_call_done = True

            self.stats.requests += 1
            try:
                html = self.adapter.fetch(url)
            except Exception as exc:
                last_error = str(exc)
                self.stats.failures += 1
                self.stats.errors.append(f"{url}: {last_error}")
                if last_error.startswith(('HTTP 404:', 'HTTP 403:', 'redirect to authentication:')):
                    break
                continue

            if looks_like_challenge(html):
                self.stats.challenges += 1
                last_error = f"WAF 挑战页（{len(html)}B）"
                continue
            return html

        self.stats.failures += 1
        raise FetchError(f"{url}: {last_error or '未知错误'}")


def build_fetcher(politeness: dict, fetcher_conf: dict, mode: Optional[str] = None,
                  fake_pages: Optional[Dict[str, str]] = None) -> RateLimitedFetcher:
    """按配置组装 fetcher。mode 优先于配置（CLI --fake 用）。"""
    mode = mode or fetcher_conf.get("mode", "stealthy")
    if mode == "fake":
        adapter = FakeFetcher(fake_pages or {})
    elif mode == "http":
        adapter = ScraplingHttpAdapter(timeout_s=int(politeness.get("timeout_ms", 30000) / 1000))
    else:
        adapter = ScraplingStealthyAdapter(
            headless=bool(fetcher_conf.get("headless", True)),
            disable_resources=bool(fetcher_conf.get("disable_resources", True)),
            timeout_ms=int(politeness.get("timeout_ms", 30000)),
        )
    return RateLimitedFetcher(
        adapter,
        min_delay=float(politeness.get("min_delay", 2.0)),
        max_delay=float(politeness.get("max_delay", 3.0)),
        max_retries=int(politeness.get("max_retries", 2)),
    )
