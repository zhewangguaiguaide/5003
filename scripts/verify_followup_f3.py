"""最小默认抓取路径实测；只写证据，不入采集数据库。"""
from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import load_config
from src.fetcher import build_fetcher, looks_like_challenge
from src.parser import extract_text


def main():
    config = load_config(str(ROOT / 'config.yaml'))
    url = 'https://www.cityu.edu.hk/admo/non-local-students/visa/student-visa'
    fetcher = build_fetcher(config['politeness'], config['fetcher'])
    report = dict(requested_url=url, mode=fetcher.adapter.name,
                  started_at=datetime.now().astimezone().isoformat(),
                  browser_live_verified=False, browser_sso_verified=False,
                  support='HTTP default; stealthy experimental and opt-in; no automatic authentication fallback')
    try:
        html = fetcher.fetch(url)
        content = extract_text(html)
        report.update(final_url=getattr(fetcher.adapter, 'last_url', url), chars=len(content),
                      challenge=looks_like_challenge(html), verified=len(content) >= 300,
                      sample=content[:250])
    except Exception as exc:
        report.update(verified=False, error=str(exc))
    report.update(finished_at=datetime.now().astimezone().isoformat())
    path = ROOT / '成员2补交_2026-10-12/docs/evidence/F3验证.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['verified'] else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
