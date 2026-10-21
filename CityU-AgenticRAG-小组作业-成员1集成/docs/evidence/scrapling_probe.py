# -*- coding: utf-8 -*-
"""Scrapling 可行性验证：抓取 CityU 3 个页面，限速 3s。"""
import sys, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from scrapling.fetchers import Fetcher

URLS = [
    "https://www.cityu.edu.hk/arro/",
    "https://www.cityu.edu.hk/lib/",
    "https://www.cityu.edu.hk/admo/",
]

for i, url in enumerate(URLS):
    if i:
        print(f"... sleep 3s (rate limit) ...")
        time.sleep(3)
    try:
        t0 = time.time()
        page = Fetcher.get(url, timeout=10)
        dt = time.time() - t0
        status = page.status
        title_el = page.css("title::text")
        title = str(title_el[0]).strip() if title_el else "(no title)"
        # 检查是否命中 Incapsula 挑战页
        raw = str(page.html_content)[:5000]
        is_challenge = ("Incapsula" in raw) or ("_Incapsula_Resource" in raw)
        text = page.get_all_text(strip=True) if not is_challenge else "(challenge page)"
        print(f"[{url}]")
        print(f"  status={status} time={dt:.1f}s challenge={is_challenge}")
        print(f"  title={title}")
        print(f"  text[:500]={text[:500]}")
        # 链接统计
        links = [str(l) for l in page.css("a::attr(href)")]
        pdf = [l for l in links if l.lower().endswith(".pdf")]
        abs_ = [l for l in links if l.startswith("http")]
        print(f"  links={len(links)} abs={len(abs_)} rel={len(links)-len(abs_)} pdf={len(pdf)}")
        print(f"  sample_links={links[:5]}")
    except Exception as e:
        print(f"[{url}] ERROR: {type(e).__name__}: {e}")
    print("-" * 60)
print("DONE")
