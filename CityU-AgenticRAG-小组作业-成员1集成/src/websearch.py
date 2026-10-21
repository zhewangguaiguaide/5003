"""联网搜索层：为 LLM 的 web_search 工具提供真实搜索后端。

与 fetcher.py 同一套"可替换适配器"思路：
- bing：curl_cffi（TLS 伪装）抓 Bing 结果页 + scrapling 解析，大陆网络可直连；
- fake：离线测试用，query -> 预置结果。

合规备注：搜索引擎结果页属事实性索引（标题/URL/摘要），
本项目只把摘要回灌给 LLM 做参考，不再分发原文全文。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


class SearchError(RuntimeError):
    """搜索后端失败（网络错误、非 200、解析无结果）。"""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


BING_SEARCH_URL = "https://www.bing.com/search"


def _first(element, selector: str):
    """scrapling 0.4.x 无 css_first；css() 返回 Selectors（list-like）。"""
    els = element.css(selector)
    return els[0] if els else None


def parse_bing_html(html: str, max_results: int = 5) -> List[SearchResult]:
    """解析 Bing 结果页（li.b_algo 结构）。抽成纯函数，便于离线测试。"""
    from scrapling.parser import Selector  # 延迟导入：与项目其他解析保持一致

    page = Selector(html)
    results: List[SearchResult] = []
    for item in page.css("li.b_algo"):
        anchor = _first(item, "h2 a")
        if anchor is None:
            continue
        title = (anchor.text or "").strip()
        url = (anchor.attrib.get("href") or "").strip()
        snippet_el = _first(item, ".b_caption p")
        if snippet_el is None:
            snippet_el = _first(item, "p")
        snippet = (snippet_el.text or "").strip() if snippet_el is not None else ""
        if title and url:
            results.append(SearchResult(title=title, url=url, snippet=snippet))
        if len(results) >= max_results:
            break
    return results


class BingSearchAdapter:
    """Bing 结果页抓取（无需 API Key；频率请自律，仅课堂演示用）。"""

    name = "bing"

    def __init__(self, market: str = "zh-HK", timeout_s: int = 15) -> None:
        self.market = market
        self.timeout_s = timeout_s

    def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        from curl_cffi import requests  # 延迟导入：离线测试无需网络库

        try:
            resp = requests.get(
                BING_SEARCH_URL,
                params={"q": query, "count": max_results, "mkt": self.market},
                impersonate="chrome",
                timeout=self.timeout_s,
            )
        except Exception as exc:
            raise SearchError(f"搜索请求失败: {exc}") from exc
        if resp.status_code != 200:
            raise SearchError(f"HTTP {resp.status_code}（Bing 结果页）")
        results = parse_bing_html(resp.text, max_results)
        if not results:
            raise SearchError("结果页解析为空（Bing 页面结构可能已变更）")
        return results


class FakeSearchAdapter:
    """离线测试适配器：按 query 前缀匹配预置结果，未命中返回默认结果。"""

    name = "fake"

    def __init__(self, pages: Optional[Dict[str, List[SearchResult]]] = None) -> None:
        self.pages = pages or {}
        self.queries: List[str] = []

    def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        self.queries.append(query)
        for key, results in self.pages.items():
            if key in query:
                return results[:max_results]
        return [SearchResult(title=f"Fake result for {query}",
                             url="https://example.com/fake",
                             snippet="offline fake snippet")][:max_results]


def build_searcher(conf: Optional[Dict[str, Any]], provider: Optional[str] = None):
    """按配置组装搜索适配器。provider 优先于配置（测试用）。"""
    conf = conf or {}
    name = provider or conf.get("provider", "bing")
    if name == "fake":
        return FakeSearchAdapter()
    if name == "bing":
        return BingSearchAdapter(
            market=conf.get("market", "zh-HK"),
            timeout_s=int(conf.get("timeout_s", 15)),
        )
    raise SearchError(f"未知搜索后端: {name}")
