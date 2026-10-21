"""解析层：HTML -> 结构化记录。

清洗是抓取工作的一部分（见 docs/Harness开发指导.md）：
- 去掉 script/style/nav/footer 等非正文内容
- 图片走 image_urls、附件走 file_urls
- date 与 crawled_at 统一为 ISO 格式，无法解析时回落
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from html import unescape
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from .storage import Record

SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "nav", "footer", "header"}
BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}

DATE_PATTERNS = (
    r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+name=["\'](?:date|pubdate|publishdate)["\'][^>]+content=["\']([^"\']+)["\']',
    r'<time[^>]+datetime=["\']([^"\']+)["\']',
)


class _Extractor(HTMLParser):
    """一次性收集正文文本、标题、链接、图片。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title = ""
        self.chunks: List[str] = []
        self.links: List[str] = []
        self.images: List[str] = []
        self.base = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        attr = dict(attrs)
        if tag == "base" and attr.get("href"):
            self.base = attr["href"]
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a" and attr.get("href"):
            self.links.append(attr["href"])
        if tag == "img":
            src = attr.get("src") or attr.get("data-src")
            if src:
                self.images.append(src)
        if tag in BLOCK_TAGS and not self._skip_depth:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS and not self._skip_depth:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._skip_depth:
            return
        if data.strip():
            self.chunks.append(data.strip())

    @property
    def text(self) -> str:
        raw = " ".join(self.chunks)
        return re.sub(r"\s*\n\s*", "\n", re.sub(r"[ \t\u00a0]+", " ", raw)).strip()


def _extract(html: str) -> _Extractor:
    ex = _Extractor()
    try:
        ex.feed(html)
        ex.close()
    except Exception:  # 容错：坏 HTML 不应中断整批抓取
        pass
    return ex


def extract_title(html: str, fallback: str = "") -> str:
    titles = re.findall(r"<title\b[^>]*>(.*?)</title>", html, re.I | re.S)
    title = re.sub(r"\s+", " ", titles[0]).strip() if titles else ""
    return clean_title(title) or fallback


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", unescape(title)).strip()
    if len(title) % 2 == 0 and title[:len(title)//2] == title[len(title)//2:]:
        title = title[:len(title)//2].strip()
    return title


def extract_text(html: str) -> str:
    return _extract(html).text


def extract_links(html: str, base_url: str) -> List[str]:
    seen, out = set(), []
    extracted = _extract(html)
    base_url = urljoin(base_url, extracted.base) if extracted.base else base_url
    for href in extracted.links:
        href = href.strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        abs_url = urljoin(base_url, href).split("#")[0]
        if urlparse(abs_url).scheme not in ('http', 'https'):
            continue
        if abs_url and abs_url not in seen:
            seen.add(abs_url)
            out.append(abs_url)
    return out


def is_navigation_only(content: str) -> bool:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return (len(content) < 400 and len(lines) >= 6
            and not any(len(line) >= 100 for line in lines))


def extract_images(html: str, base_url: str) -> List[str]:
    return [urljoin(base_url, src) for src in _extract(html).images][:50]


def extract_file_urls(links: List[str]) -> List[str]:
    """附件（PDF/Office 文件）不计入详情页，只记在 file_urls。"""
    exts = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".zip")
    return [u for u in links if u.lower().split("?")[0].endswith(exts)]


def extract_date(html: str) -> str:
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:32]
    m = re.search(r"(\d{4})[-/年]\s*(\d{1,2})[-/月]\s*(\d{1,2})", html)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def parse_detail(html: str, url: str, topic: str = "", column: str = "") -> Record:
    """把详情页 HTML 解析成一条 Record（不清洗就入库是不允许的）。"""
    links = extract_links(html, url)
    host = urlparse(url).netloc
    return Record(
        url=url,
        title=extract_title(html, fallback=url),
        source=host,
        content=extract_text(html),
        date=extract_date(html),
        image_urls=extract_images(html, url),
        file_urls=extract_file_urls(links),
        topic=topic,
        column=column,
    )
