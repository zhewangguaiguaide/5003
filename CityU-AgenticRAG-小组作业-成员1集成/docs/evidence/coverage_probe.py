"""内容覆盖核查探针：逐栏目实测种子页"能爬到什么、细度如何"。

用途（docs/可行性研究.md 的二轮核查）：
1. 每个栏目种子页实测：是否过 WAF、标题、正文长度、日期、附件/图片数；
2. 页面链接归类：本栏目内链接 / 其他已知学生服务部门链接 / 意外发现链接；
3. 正文关键词命中（career/counselling/health 等），记录"意料之外但同属
   学生服务方向"的信息，供扩充主题清单参考。

产出：docs/evidence/raw-logs/coverage_probe.json
运行：source .venv/Scripts/activate && python docs/evidence/coverage_probe.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src import config as cfg
from src.fetcher import FetchError, build_fetcher, looks_like_challenge
from src.parser import extract_links, parse_detail

# 已知的 8 主题对应部门前缀（出现即"预期内"）
KNOWN_DEPTS = {"admo", "arro", "fo", "sds", "sro", "geo", "sgs", "lib", "pg"}
# 导航/通用路径，不算"意外发现"
IGNORE_PREFIXES = {
    "", "about", "about-cityu", "news", "events", "media", "people", "research",
    "ceng", "main", "home", "en", "zh-hk", "zh-cn", "search", "contact",
    "footer", "header", "sitemap", "a-z", "az", "covid-19", "www6",
}
# 正文关键词 watchlist：同属学生服务方向但未必在 8 主题内
WATCH_TERMS = [
    "career", "counselling", "counseling", "health", "insurance", "mental",
    "wellbeing", "well-being", "sports", "orientation", "buddy", "mentor",
    "exchange", "canteen", "catering", "chaplain", "disability", "emergency",
    "scholarship", "bursary", "octopus", "bank", "IT service", "WiFi", "email account",
    "student card", "locker", "transport", "dental", "clinic",
]


def classify_links(links, column):
    same_column, other_known, unexpected = [], [], []
    for url in links:
        host = urlparse(url).netloc.lower()
        if "cityu.edu.hk" not in host:
            continue
        path = urlparse(url).path.strip("/")
        first = path.split("/")[0].lower() if path else ""
        if first in IGNORE_PREFIXES:
            continue
        if any(inc.strip("/").lower() in url.lower() for inc in column.include if inc):
            same_column.append(url)  # 与 crawler.py 一致：对完整 URL 匹配（含 host）
        elif first in KNOWN_DEPTS:
            other_known.append(url)
        elif re.fullmatch(r"[a-z][a-z0-9-]{1,15}", first):
            unexpected.append(url)
    return same_column, other_known, unexpected


def main() -> int:
    config = cfg.load_config()
    columns = cfg.build_columns(config)
    politeness = config.get("politeness") or {}
    fetcher = build_fetcher(politeness, config.get("fetcher") or {})

    results = []
    for column in columns:
        for seed in column.seeds:
            item = {"column": column.name, "topic": column.topic, "url": seed}
            try:
                html = fetcher.fetch(seed)
            except FetchError as exc:
                item.update(ok=False, error=str(exc)[:200])
                results.append(item)
                print(f"[FAIL] {column.name:12s} {seed}\n       {str(exc)[:120]}")
                continue
            record = parse_detail(html, seed, topic=column.topic, column=column.name)
            links = extract_links(html, seed)
            same, other, unexpected = classify_links(links, column)
            text_lower = record.content.lower()
            hits = {t: text_lower.count(t.lower()) for t in WATCH_TERMS}
            hits = {t: c for t, c in hits.items() if c}
            item.update(
                ok=not looks_like_challenge(html),
                html_len=len(html),
                title=record.title[:120],
                content_len=len(record.content),
                date=record.date,
                n_files=len(record.file_urls),
                n_images=len(record.image_urls),
                n_links_same_column=len(set(same)),
                links_other_known=sorted(set(other))[:20],
                links_unexpected=sorted(set(unexpected))[:30],
                watch_hits=hits,
                content_head=record.content[:800],
            )
            results.append(item)
            print(f"[{'OK ' if item['ok'] else 'CHAL'}] {column.name:12s} "
                  f"len={item['content_len']:6d} files={item['n_files']:2d} "
                  f"imgs={item['n_images']:2d} | {item['title'][:70]}")

    out = os.path.join(os.path.dirname(__file__), "raw-logs", "coverage_probe.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    stats = fetcher.stats
    print(f"\n请求={stats.requests} 挑战页={stats.challenges} 失败={stats.failures}")
    print(f"结果已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
