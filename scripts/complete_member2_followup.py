"""生成 F1/F2 完整语料补交及差异证据，不修改接收方数据库。"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import config
from src.corpus import export_jsonl, quality_report
from src.storage import SQLiteStorage


def main():
    package = ROOT / '成员2补交_2026-10-12'
    old_path = package / '附件/返工前/data/corpus.jsonl'
    old = {r['url']: r for r in map(json.loads, old_path.read_text(encoding='utf-8').splitlines())}
    storage = SQLiteStorage(str(ROOT / 'data/cityu_faq.db'))
    try:
        records = storage.all_records()
    finally:
        storage.close()
    corpus = ROOT / 'data/corpus.jsonl'
    stats = export_jsonl(records, str(corpus))
    current = {r['url']: r for r in map(json.loads, corpus.read_text(encoding='utf-8').splitlines())}
    report = quality_report(records, config.build_columns(config.load_config(str(ROOT / 'config.yaml'))))
    report.update(corpus_sha256=hashlib.sha256(corpus.read_bytes()).hexdigest(),
                  generated_at=datetime.now().astimezone().isoformat(),
                  scope='F1/F2 offline re-export of historical records; not full live refresh',
                  semantic_review='targeted_F1_F2_verified; final_receiver_review_pending',
                  release_ready=False)
    (ROOT / 'data/quality_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    changes = dict(before_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest(),
                   after_sha256=report['corpus_sha256'], before_count=len(old), after_count=len(current),
                   added=sorted(current.keys()-old.keys()), removed=sorted(old.keys()-current.keys()),
                   fields_changed=[dict(url=u, fields={k: dict(before=old[u][k], after=current[u][k])
                                       for k in current[u] if current[u][k] != old[u][k]})
                                   for u in sorted(current.keys() & old.keys()) if old[u] != current[u]],
                   stats=stats, coverage=report['coverage'], seed_success=report['seed_success'])
    evidence = package / 'docs/evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / '语料变化.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    audit = [json.loads(line) for line in (ROOT / 'data/crawl_audit.jsonl').read_text(encoding='utf-8').splitlines()]
    names = set(report['coverage'])
    (package / 'data').mkdir(parents=True, exist_ok=True)
    for file in ('corpus.jsonl', 'quality_report.json'):
        shutil.copy2(ROOT / 'data' / file, package / 'data' / file)
    (package / 'data/crawl_audit.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in audit if row.get('column') in names), encoding='utf-8')
    (evidence / '审计说明.json').write_text(json.dumps(dict(historical=True, rerun_this_round=False,
        source='data/crawl_audit.jsonl', total_lines=len(audit), delivered_lines=sum(r.get('column') in names for r in audit),
        excluded_test_lines=sum(r.get('column') not in names for r in audit)), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(changes, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
