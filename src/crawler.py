"""爬虫层：列表页 + 详情页，栈式增量、幂等。

严格复刻 docs/Harness开发指导.md 里的数据结构（课外资料的核心方法学）：
1. 扫描列表页，把详情页 URL 入栈，**不写库**；
2. 遇到终止条件（该 URL 已在库中）就停止扫描；
3. 之后从栈顶出栈，抓详情、清洗、入库。

于是"从新到旧入栈、从旧到新入库"，中途崩溃重跑也不会漏数据（幂等）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

from . import parser as _parser
from .fetcher import FetchError
from .storage import Record

NON_DETAIL_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
                   ".zip", ".jpg", ".jpeg", ".png", ".gif", ".mp4", ".webp")

# 默认排除：登录/SSO/员工名录等非学生服务正文（实测抓取时发现的污染源）
DEFAULT_EXCLUDE = ("_spauth", "login", "logout", "signin", "sso", "saml",
                   "staffdir", "staff-dir", "StaffDir", "webmail", "intranet")


@dataclass
class ColumnSpec:
    """一个栏目（一个主题下的一组页面）。"""

    name: str
    topic: str = ""
    seeds: List[str] = field(default_factory=list)
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    max_pages: int = 20
    capture_seeds: bool = False


@dataclass
class CrawlStats:
    column: str = ""
    list_pages: int = 0
    detail_pages: int = 0
    new_records: int = 0
    updated_records: int = 0
    skipped_old: int = 0
    skipped_thin: int = 0
    stop_reason: str = ""
    errors: List[str] = field(default_factory=list)
    repaired: int = 0

    def summary(self) -> str:
        return (f"[{self.column}] 列表页={self.list_pages} 详情页={self.detail_pages} "
                f"新增={self.new_records} 更新={self.updated_records} 过旧跳过={self.skipped_old} "
                f"空壳跳过={self.skipped_thin} "
                f"修复={self.repaired} "
                f"停止原因={self.stop_reason or '-'} 错误={len(self.errors)}")


def default_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ColumnCrawler:
    """栏目级爬虫：对外只暴露 fetch_list_page / fetch_detail / crawl（同 Harness 接口）。"""

    def __init__(self, column: ColumnSpec, fetcher, storage,
                 now: Callable[[], str] = default_now,
                 min_date: Optional[str] = None,
                 max_consecutive_404: int = 3,
                 min_content_len: int = 300) -> None:
        self.column = column
        self.fetcher = fetcher
        self.storage = storage
        self.now = now
        self.min_date = min_date
        self.max_consecutive_404 = max_consecutive_404
        self.min_content_len = min_content_len

    # ---- 列表页 ----------------------------------------------------------
    def is_detail_link(self, url: str, list_url: str) -> bool:
        if url.split("#")[0] == list_url.split("#")[0]:
            return False
        if url.lower().split("?")[0].endswith(NON_DETAIL_EXTS):
            return False
        for pattern in list(DEFAULT_EXCLUDE) + list(self.column.exclude):
            if pattern.lower() in url.lower():
                return False
        if self.column.include:
            if not any(pattern in url for pattern in self.column.include):
                return False
        else:
            if urlparse(url).netloc != urlparse(list_url).netloc:
                return False
        return True

    def fetch_list_page(self, url: str) -> List[str]:
        """抓列表页并解析出详情页 URL。**不取正文、不写库**（eval 项 2 依赖此约定）。"""
        html = self.fetcher.fetch(url)
        return [u for u in _parser.extract_links(html, url) if self.is_detail_link(u, url)]

    # ---- 详情页 ----------------------------------------------------------
    def fetch_detail(self, url: str) -> Record:
        html = self.fetcher.fetch(url)
        record = _parser.parse_detail(html, url, topic=self.column.topic, column=self.column.name)
        record.crawled_at = self.now()
        if not record.date:            # 兜底：无法解析发布日期就用抓取时间
            record.date = record.crawled_at
        return record

    # ---- 主流程 ----------------------------------------------------------
    def crawl(self, repair_loops: int = 1) -> CrawlStats:
        stats = CrawlStats(column=self.column.name)
        stack: List[str] = []
        seen: set = set()
        consecutive_404 = 0
        stop = False

        for list_url in self.column.seeds:
            if stop or stats.list_pages >= self.column.max_pages:
                break
            try:
                detail_urls = self.fetch_list_page(list_url)
            except FetchError as exc:
                consecutive_404 += 1
                stats.errors.append(f"list:{list_url}: {exc}")
                if not self.storage.exists(list_url):
                    self.storage.upsert(Record(url=list_url, error=str(exc), column=self.column.name,
                                              topic=self.column.topic, crawled_at=self.now()))
                if consecutive_404 >= self.max_consecutive_404:
                    stats.stop_reason = f"连续 {consecutive_404} 次列表页失败"
                    break
                continue

            consecutive_404 = 0
            stats.list_pages += 1
            if self.column.capture_seeds and not self.storage.exists(list_url):
                seen.add(list_url)
                stack.append(list_url)
            for detail_url in detail_urls:
                if self.storage.exists(detail_url):      # 终止条件：URL 已在库中
                    stop = True
                    stats.stop_reason = "命中已入库 URL（增量终止）"
                    break
                if detail_url in seen:
                    continue
                seen.add(detail_url)
                stack.append(detail_url)                 # 只入栈，不写库
                if len(stack) >= self.column.max_pages:
                    stop = True
                    stats.stop_reason = f"达到页面预算 max_pages={self.column.max_pages}"
                    break
        else:
            if not stats.stop_reason:
                stats.stop_reason = "种子列表页扫描完毕"

        self._drain(stack, stats)
        # 首轮失败 URL 单独回放，避免一个瞬时超时让全量语料留下缺口。
        for _ in range(max(0, repair_loops)):
            failed = [e[len("detail:"):].split(": ", 1)[0]
                      for e in stats.errors if e.startswith("detail:")]
            if not failed:
                break
            before = len(stats.errors)
            retry_stack = []
            for url in dict.fromkeys(failed):
                retry_stack.append(url)
            stats.errors = [e for e in stats.errors if not e.startswith("detail:")]
            self._drain(retry_stack, stats)
            stats.repaired += before - len(stats.errors)
        return stats

    def crawl_full(self, repair_loops: int = 2) -> CrawlStats:
        """所有种子优先采集，已有链接跳过但不终止；预算包含种子。"""
        import json
        from pathlib import Path
        stats = CrawlStats(column=self.column.name)
        links = []
        events = []
        def collect(url):
            for attempt in range(repair_loops + 1):
                try:
                    html = self.fetcher.fetch(url)
                    record = _parser.parse_detail(html, url, self.column.topic, self.column.name)
                    record.crawled_at = self.now()
                    record.date = record.date or record.crawled_at
                    if self.min_date and record.date < self.min_date:
                        stats.skipped_old += 1
                        events.append(dict(url=url, attempt=attempt, status="old"))
                        return html
                    if len(record.content) < self.min_content_len or _parser.is_navigation_only(record.content):
                        raise FetchError(f"thin/navigation content ({len(record.content)} chars)")
                    if self.storage.upsert(record):
                        stats.new_records += 1
                    else:
                        stats.updated_records += 1
                    stats.detail_pages += 1
                    stats.repaired += int(attempt > 0)
                    events.append(dict(url=url, attempt=attempt, status="ok", chars=len(record.content)))
                    return html
                except FetchError as exc:
                    events.append(dict(url=url, attempt=attempt, status="error", error=str(exc)))
                    if any(marker in str(exc) for marker in ('HTTP 404:', 'HTTP 403:', 'redirect to authentication:')):
                        break
            message = str(events[-1]["error"])
            if message.startswith("thin/navigation"):
                stats.skipped_thin += 1
            # 成功原文保留；失败审计始终落日志，首次失败另存 error 记录。
            if not self.storage.exists(url):
                self.storage.upsert(Record(url=url, source=urlparse(url).netloc,
                                          topic=self.column.topic, column=self.column.name,
                                          error=message, crawled_at=self.now()))
            stats.errors.append(f"detail:{url}: {message}")
            return ""
        try:
            for seed in self.column.seeds:
                html = collect(seed)
                stats.list_pages += 1
                if html:
                    links.extend(u for u in _parser.extract_links(html, seed)
                                 if self.is_detail_link(u, seed))
            budget = max(0, self.column.max_pages - len(self.column.seeds))
            attempted = 0
            for url in dict.fromkeys(links):
                if url in self.column.seeds or self.storage.exists(url):
                    continue
                if attempted >= budget:
                    break
                collect(url)
                attempted += 1
            stats.stop_reason = f"全量种子扫描完成；新详情尝试={attempted}/{budget}"
            return stats
        finally:
            path = Path("data/crawl_audit.jsonl")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(dict(column=self.column.name, time=self.now(),
                                         events=events, stats=stats.__dict__), ensure_ascii=False) + "\n")

    def _drain(self, stack: List[str], stats: CrawlStats) -> None:
        """LIFO 出栈抓详情：先入后出，保证幂等与"从旧到新"入库顺序。"""
        while stack:
            url = stack.pop()
            try:
                record = self.fetch_detail(url)
            except FetchError as exc:
                stats.errors.append(f"detail:{url}: {exc}")
                if not self.storage.exists(url):
                    self.storage.upsert(Record(url=url, error=str(exc), column=self.column.name,
                                              topic=self.column.topic, crawled_at=self.now()))
                continue
            stats.detail_pages += 1
            if self.min_date and record.date and record.date < self.min_date:
                stats.skipped_old += 1
                continue
            if len(record.content) < self.min_content_len or _parser.is_navigation_only(record.content):
                stats.skipped_thin += 1
                continue
            if self.storage.upsert(record):
                stats.new_records += 1
            else:
                stats.updated_records += 1


class DomainCrawler:
    """域名级爬虫：统一管理各栏目（同 Harness 接口）。"""

    def __init__(self, columns: List[ColumnSpec], fetcher, storage,
                 now: Callable[[], str] = default_now,
                 min_date: Optional[str] = None,
                 max_consecutive_404: int = 3,
                 min_content_len: int = 300) -> None:
        self.columns = columns
        self.fetcher = fetcher
        self.storage = storage
        self.now = now
        self.min_date = min_date
        self.max_consecutive_404 = max_consecutive_404
        self.min_content_len = min_content_len

    def crawl(self, repair_loops: int = 1, full: bool = False) -> Dict[str, CrawlStats]:
        results: Dict[str, CrawlStats] = {}
        for column in self.columns:
            started_at = self.now()
            crawler = ColumnCrawler(column, self.fetcher, self.storage, now=self.now,
                                    min_date=self.min_date,
                                    max_consecutive_404=self.max_consecutive_404,
                                    min_content_len=self.min_content_len)
            results[column.name] = (crawler.crawl_full(repair_loops) if full
                                    else crawler.crawl(repair_loops=repair_loops))
            if hasattr(self.storage, "path"):
                import sqlite3
                from .db import init_schema, log_crawl_run
                stats = results[column.name]
                with sqlite3.connect(self.storage.path) as conn:
                    init_schema(conn)
                    log_crawl_run(conn, column.name, started_at, self.now(), stats.new_records,
                                  stats.skipped_old + stats.skipped_thin, len(stats.errors))
        return results
