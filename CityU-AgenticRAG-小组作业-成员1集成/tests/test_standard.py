"""标准化集成测试 = 爬虫 Harness 的 eval（全部离线，不联网）。

评估项（对齐 docs/Harness开发指导.md）：
1. 详情页爬取：url/标题/来源/时间/内容均不为空
2. 列表页爬取：返回 URL 但不取正文（不写库）——证明"URL 入栈、出栈才取内容"
3. 爬取顺序先入后出：按 date 排序 == 按 crawled_at 排序
4. 达到最小日期停止：只入库不早于 min_date 的内容
5. 大颗粒度增量：再爬一次应无新增
6. 小颗粒度增量：exists 检查恰好等于 3 次且停止条件生效
另加：WAF 挑战页判定与重试、限速策略。

代码量与爬虫规模无关（新增栏目不需要改测试）。
运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timedelta

from src.crawler import ColumnCrawler, DomainCrawler
from src.fetcher import (FakeFetcher, FetchError, RateLimitedFetcher,
                         looks_like_challenge)
from src.parser import extract_date, extract_text, parse_detail
from src.storage import MockStorage

from tests.mock_site import HOST, LIST_1, LIST_2, build_mock_column, build_mock_site


class FakeClock:
    """确定性时钟：每次调用前进 1 分钟，保证 crawled_at 严格递增。"""

    def __init__(self) -> None:
        self._t = datetime(2026, 9, 25, 10, 0, 0)

    def __call__(self) -> str:
        self._t += timedelta(minutes=1)
        return self._t.isoformat(timespec="seconds")


def make_fetcher(pages=None):
    pages = pages if pages is not None else build_mock_site()
    return RateLimitedFetcher(FakeFetcher(pages), min_delay=0.0, max_delay=0.0,
                              max_retries=0, sleep=lambda _s: None)


def make_crawler(storage, **kwargs):
    return ColumnCrawler(build_mock_column(**kwargs), make_fetcher(), storage,
                         now=FakeClock(), max_consecutive_404=3)


class TestStandardEval(unittest.TestCase):
    # ---- eval 1: 详情页爬取 -------------------------------------------
    def test_01_detail_page_fields_non_empty(self):
        crawler = make_crawler(MockStorage())
        record = crawler.fetch_detail(f"{HOST}/doc/d1.htm")
        for field in ("url", "title", "source", "date", "content", "crawled_at"):
            self.assertTrue(getattr(record, field), f"{field} 不应为空")
        self.assertEqual(record.title, "News 1")
        self.assertIn("Body of news 1", record.content)
        self.assertIn("2026-09-01", record.date)
        self.assertTrue(any(u.endswith(".pdf") for u in record.file_urls))
        self.assertTrue(any(u.endswith(".png") for u in record.image_urls))

    # ---- eval 2: 列表页爬取（只拿 URL，不写库） ------------------------
    def test_02_list_page_returns_urls_without_writing_db(self):
        storage = MockStorage()
        crawler = make_crawler(storage)
        urls = crawler.fetch_list_page(LIST_1)
        self.assertEqual(len(urls), 3)
        self.assertTrue(all("/doc/" in u for u in urls))
        self.assertNotIn(f"{HOST}/about.htm", urls)   # include 过滤生效
        self.assertNotIn(f"{HOST}/_spauth/_login.aspx", urls)   # 登录页排除
        self.assertNotIn(f"{HOST}/staff/StaffDir.htm", urls)    # 员工名录排除
        self.assertEqual(storage.count(), 0)          # 关键：列表页阶段不写库
        self.assertEqual(storage.upsert_calls, 0)

    # ---- eval 3: 先入后出 --------------------------------------------
    def test_03_crawl_order_is_lifo(self):
        storage = MockStorage()
        stats = make_crawler(storage).crawl()
        self.assertEqual(stats.new_records, 6)
        records = storage.all_records()
        by_crawled = [r.date for r in sorted(records, key=lambda r: r.crawled_at)]
        self.assertEqual(by_crawled, sorted(r.date for r in records))
        self.assertEqual([r.title for r in sorted(records, key=lambda r: r.crawled_at)],
                         [f"News {i}" for i in range(1, 7)])

    # ---- eval 4: 最小日期停止 ----------------------------------------
    def test_04_min_date_filters_old_records(self):
        storage = MockStorage()
        crawler = ColumnCrawler(build_mock_column(), make_fetcher(), storage,
                                now=FakeClock(), min_date="2026-09-04T00:00:00")
        stats = crawler.crawl()
        self.assertEqual(storage.count(), 3)
        self.assertEqual(stats.skipped_old, 3)
        self.assertTrue(all(r.date >= "2026-09-04" for r in storage.all_records()))

    # ---- eval 5: 大颗粒度增量 ----------------------------------------
    def test_05_second_crawl_adds_nothing(self):
        storage = MockStorage()
        first = make_crawler(storage).crawl()
        self.assertEqual(first.new_records, 6)
        second = make_crawler(storage).crawl()
        self.assertEqual(second.new_records, 0)
        self.assertEqual(second.detail_pages, 0)      # 一命中已入库就停止扫描
        self.assertIn("增量终止", second.stop_reason)
        self.assertEqual(storage.count(), 6)

    # ---- eval 6: 小颗粒度增量 ----------------------------------------
    def test_06_small_granularity_increment(self):
        storage = MockStorage(exists_after=3)
        stats = make_crawler(storage).crawl()
        self.assertEqual(storage.exists_calls, 3, "停止条件检查次数应恰好为 3")
        self.assertEqual(stats.new_records, 2)
        self.assertEqual(storage.count(), 2)

    # ---- eval 7: 空壳页不入库 ----------------------------------------
    def test_07_thin_page_skipped(self):
        pages = build_mock_site()
        pages[LIST_1] = ('<html><head><title>L</title></head><body><ul>'
                         '<li><a href="/doc/d1.htm">d1</a></li>'
                         '<li><a href="/doc/thin.htm">thin</a></li>'
                         '</ul></body></html>')
        pages[f"{HOST}/doc/thin.htm"] = (
            '<html><head><title>Thin</title></head><body><p>tiny</p></body></html>')
        storage = MockStorage()
        column = build_mock_column(max_pages=5)
        column.seeds = [LIST_1]
        crawler = ColumnCrawler(column, make_fetcher(pages), storage, now=FakeClock(),
                                min_content_len=300)
        stats = crawler.crawl()
        self.assertEqual(stats.skipped_thin, 1)
        self.assertEqual(storage.count(), 1)
        self.assertEqual(storage.all_records()[0].title, "News 1")


class TestFetcherAndParser(unittest.TestCase):
    def test_challenge_detection(self):
        challenge = ('<html><head><META NAME="ROBOTS" CONTENT="NOINDEX, NOFOLLOW"></head>'
                     '<body><iframe src="/_Incapsula_Resource?SWJIYLWA=1&incident_id=2"></iframe>'
                     "</body></html>")
        self.assertTrue(looks_like_challenge(challenge))
        self.assertTrue(looks_like_challenge(""))
        # 实测教训：正常大页面里同样含 _Incapsula_Resource，不能误判
        real_page = "<html><body>" + ("x" * 30000) + "/_Incapsula_Resource</body></html>"
        self.assertFalse(looks_like_challenge(real_page))

    def test_rate_limited_fetcher_retries_challenge(self):
        challenge = '<html><body><iframe src="/_Incapsula_Resource?incident_id=1"></iframe></body></html>'
        real = "<html><body>" + ("good " * 5000) + "</body></html>"

        class Flaky:
            def __init__(self):
                self.n = 0

            def fetch(self, url):
                self.n += 1
                return challenge if self.n < 2 else real

        fetcher = RateLimitedFetcher(Flaky(), min_delay=0, max_delay=0, max_retries=2,
                                     sleep=lambda _s: None)
        self.assertEqual(fetcher.fetch("https://x.test/a"), real)
        self.assertEqual(fetcher.stats.challenges, 1)

    def test_rate_limited_fetcher_gives_up(self):
        class AlwaysChallenge:
            def fetch(self, url):
                return '<iframe src="/_Incapsula_Resource?incident_id=1"></iframe>'

        fetcher = RateLimitedFetcher(AlwaysChallenge(), min_delay=0, max_delay=0,
                                     max_retries=1, sleep=lambda _s: None)
        with self.assertRaises(FetchError):
            fetcher.fetch("https://x.test/a")

    def test_parser_handles_missing_date(self):
        html = "<html><head><title>T</title></head><body><p>hello world</p></body></html>"
        record = parse_detail(html, f"{HOST}/doc/x.htm")
        self.assertEqual(record.date, "")
        self.assertEqual(record.title, "T")
        self.assertIn("hello world", record.content)
        self.assertEqual(extract_date("<time datetime='2026-01-02'>x</time>"), "2026-01-02")
        self.assertIn("hello", extract_text(html))


class TestDomainCrawler(unittest.TestCase):
    def test_domain_crawler_manages_columns(self):
        storage = MockStorage()
        first = build_mock_column()
        second = dataclasses.replace(build_mock_column(), name="mock2")
        results = DomainCrawler([first, second], make_fetcher(), storage, now=FakeClock()).crawl()
        self.assertEqual(set(results), {"mock", "mock2"})
        self.assertEqual(results["mock"].new_records, 6)
        # 第二列指向同一批 URL，已入库 -> 增量终止，无新增
        self.assertEqual(results["mock2"].new_records, 0)
        self.assertEqual(storage.count(), 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
