"""语料质检与导出。

成员 2 的交付层：把采集层的 Record 规范化为稳定的 JSONL 语料。
这里不改数据库 schema，因而可以独立交接给存储层和检索层使用。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .storage import Record
from .parser import is_navigation_only, clean_title

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                    "gclid", "fbclid", "_ga"}
_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})\s*[-/–—]\s*(?:(20\d{2})|(2\d))(?!\d)")
_WS_RE = re.compile(r"\s+")


def canonicalize_url(url: str) -> str:
    """去掉片段、追踪参数和无意义的尾斜杠，保留业务 query 参数。"""
    parts = urlsplit((url or "").strip())
    host = parts.hostname.lower() if parts.hostname else ""
    if not host:
        return url.strip()
    port = parts.port
    if port and not ((parts.scheme.lower() == "http" and port == 80) or
                     (parts.scheme.lower() == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in _TRACKING_PARAMS]
    query.sort()
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query), ""))


def normalize_text(text: str) -> str:
    """用于指纹比较的文本规范化；不改变导出的原文。"""
    return _WS_RE.sub(" ", (text or "").replace("\u00a0", " ")).strip().lower()


def infer_academic_year(record: Record) -> str:
    """从标题、URL、正文和日期推断学年，找不到时返回空字符串。"""
    haystack = " ".join((record.title, record.url, record.content[:12000], record.date))
    matches = _YEAR_RE.findall(haystack)
    if matches:
        # 取最后出现的学年，通常是页面当前/最新学年。
        start, full_end, short_end = matches[-1]
        end = full_end or f"20{short_end}"
        return f"{start}-{end}"
    # 单独的年份可能只是发布日期/版权年份，不能冒充学年。
    return ""


def _quality_key(record: Record) -> Tuple[int, int, str]:
    """重复记录择优：正文长、附件多、抓取时间新。"""
    return (len(normalize_text(record.content)),
            len(record.file_urls) + len(record.image_urls),
            record.crawled_at or "")


def deduplicate(records: Iterable[Record]) -> Tuple[List[Record], dict]:
    """按规范化 URL + 正文指纹去重，返回稳定排序的记录和质检统计。"""
    records = list(records)
    input_count = len(records)
    records = [r for r in records if not r.error and r.content.strip()
               and not is_navigation_only(r.content)]
    by_url = {}
    dropped_url = 0
    for record in records:
        key = canonicalize_url(record.url)
        current = by_url.get(key)
        if current is None or _quality_key(record) > _quality_key(current):
            if current is not None:
                dropped_url += 1
            by_url[key] = record
        else:
            dropped_url += 1

    by_content = {}
    dropped_content = 0
    for record in by_url.values():
        fingerprint = hashlib.sha256(normalize_text(record.content).encode("utf-8")).hexdigest()
        current = by_content.get(fingerprint)
        if current is None or _quality_key(record) > _quality_key(current):
            if current is not None:
                dropped_content += 1
            by_content[fingerprint] = record
        else:
            dropped_content += 1

    output = sorted(by_content.values(), key=lambda r: (r.column, canonicalize_url(r.url)))
    return output, {
        "input": input_count,
        "rejected": input_count - len(records),
        "output": len(output),
        "dropped_url": dropped_url,
        "dropped_content": dropped_content,
    }


def record_to_corpus_row(record: Record) -> dict:
    row = asdict(record)
    row["url"] = canonicalize_url(record.url)
    row["content"] = record.content.strip()
    row["title"] = clean_title(record.title or "")
    row["source"] = urlsplit(record.url).netloc.lower()
    row["academic_year"] = infer_academic_year(record)
    return row


def export_jsonl(records: Iterable[Record], path: str) -> dict:
    records = list(records)
    unique, stats = deduplicate(records)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as fh:
        for record in unique:
            fh.write(json.dumps(record_to_corpus_row(record), ensure_ascii=False) + "\n")
    stats["path"] = str(target)
    return stats


def quality_report(records: Iterable[Record], columns) -> dict:
    records = list(records)
    unique, stats = deduplicate(records)
    valid_urls = {canonicalize_url(r.url) for r in unique}
    fingerprints = {normalize_text(r.content) for r in unique}
    by_url = {canonicalize_url(r.url): r for r in records}
    seeds = []
    for column in columns:
        for url in column.seeds:
            row = by_url.get(canonicalize_url(url))
            status = 'missing'
            if row and row.error:
                status = 'error'
            elif row and canonicalize_url(url) in valid_urls:
                status = 'ok'
            elif row and normalize_text(row.content) in fingerprints:
                status = 'deduplicated_alias'
            seeds.append(dict(column=column.name, url=url, status=status,
                              chars=len(row.content) if row else 0,
                              error=row.error if row else ''))
    return dict(stats=stats, seeds=seeds,
                coverage={c.name: sum(r.column == c.name for r in unique) for c in columns},
                seed_success=sum(s['status'] in ('ok', 'deduplicated_alias') for s in seeds))
