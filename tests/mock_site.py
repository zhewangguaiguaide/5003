"""离线 mock 站点：给标准化集成测试与 --mode fake 用，不联网。"""
from __future__ import annotations

from typing import Dict

from src.crawler import ColumnSpec

HOST = "https://mock.cityu.test"
LIST_1 = f"{HOST}/list/page1.htm"   # 最新一页（列表页头部 = 最新）
LIST_2 = f"{HOST}/list/page2.htm"   # 更旧一页
NEWEST_DAY = 6                      # d1 最旧、d6 最新


def _list_page(days) -> str:
    items = "\n".join(
        f'<li><a href="/doc/d{day}.htm">News {day}</a></li>' for day in days
    )
    return f"""<html><head><title>Mock News List</title></head><body>
<nav><a href="/about.htm">About</a>
<a href="/_spauth/_login.aspx">Login</a>
<a href="/staff/StaffDir.htm">Staff</a></nav>
<ul>
{items}
</ul>
</body></html>"""


def _detail_page(day: int) -> str:
    body = " ".join([
        f"Body of news {day}. CityU student service FAQ sample content.",
        "Non-local students must obtain a student visa or entry permit before arrival.",
        "Applications are processed on a rolling basis and early applications are encouraged.",
        "Tuition fees are charged per semester and payable by the published due date.",
    ] * 3)
    return f'''<html><head>
<title>News {day}</title>
<meta property='article:published_time' content='2026-09-{day:02d}T09:00:00+08:00'>
</head><body>
<h1>News {day}</h1>
<p>{body}</p>
<p><a href='/files/n{day}.pdf'>attachment</a></p>
<img src='/img/n{day}.png' alt='fig'>
</body></html>'''


def build_mock_site() -> Dict[str, str]:
    pages: Dict[str, str] = {
        LIST_1: _list_page([6, 5, 4]),
        LIST_2: _list_page([3, 2, 1]),
        f"{HOST}/about.htm": "<html><head><title>About</title></head><body><p>about</p></body></html>",
    }
    for day in range(1, NEWEST_DAY + 1):
        pages[f"{HOST}/doc/d{day}.htm"] = _detail_page(day)
    return pages


def build_mock_column(max_pages: int = 20) -> ColumnSpec:
    return ColumnSpec(
        name="mock",
        topic="mock 主题",
        seeds=[LIST_1, LIST_2],
        include=["/doc/"],
        max_pages=max_pages,
    )
