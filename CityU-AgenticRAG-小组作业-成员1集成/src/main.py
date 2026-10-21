"""CLI 入口。

用法：
  python -m src.main --dry-run                # 默认：只打印抓取计划，不联网
  python -m src.main --live                   # 实际抓取（stealthy 无头浏览器）
  python -m src.main --live --column fees     # 只抓某个栏目
  python -m src.main --live --mode fake       # 用内置 mock 站点跑通全流程（离线）
  python -m src.main --smoke <URL>            # 只抓一页，报告长度/是否挑战页
  python -m src.main --status                 # 查看已入库统计
  python -m src.main --export data/corpus.jsonl
  python -m src.main --migrate               # 原始 records 库迁移，快照库禁止
  python -m src.main --import-corpus data/corpus.jsonl # JSONL 完整快照接收
  python -m src.main --quality --quality-source documents # 活动文档接收质检
  python -m src.main --ask "非本地生签证怎么办"   # DeepSeek + web_search 联网问答
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

from . import config as cfg
from .crawler import DomainCrawler
from .fetcher import FetchError, build_fetcher, looks_like_challenge, RateLimitedFetcher
from .storage import SQLiteStorage


def _fix_console_encoding() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass


def cmd_dry_run(columns, columns_filter) -> int:
    total = 0
    print("=== DRY RUN（不联网，仅打印抓取计划）===")
    for column in columns:
        if columns_filter and column.name not in columns_filter:
            continue
        print(f"\n[{column.name}] 主题={column.topic or '-'} 预算 max_pages={column.max_pages}")
        for seed in column.seeds:
            print(f"  seed  {seed}")
        print(f"  include 过滤: {column.include or '(同域名)'}")
        total += len(column.seeds)
    print(f"\n共 {total} 个种子页面。确认合规后加 --live 实际抓取。")
    return 0


def cmd_status(storage) -> int:
    print(f"库中共 {storage.count()} 条记录")
    by_column = {}
    for record in storage.all_records():
        by_column.setdefault(record.column or "-", 0)
        by_column[record.column or "-"] += 1
    for name, count in sorted(by_column.items()):
        print(f"  {name}: {count}")
    return 0


def cmd_smoke(fetcher, url: str) -> int:
    try:
        html = fetcher.fetch(url)
    except FetchError as exc:
        print(f"[FAIL] {url}\n  {exc}")
        return 1
    print(f"[OK] {url}")
    print(f"  HTML 长度={len(html)}  挑战页={looks_like_challenge(html)}")
    from .parser import extract_text, extract_title

    print(f"  标题={extract_title(html)[:120]}")
    print(f"  正文前 200 字={extract_text(html)[:200]}")
    return 0


def cmd_export(storage, path: str) -> int:
    from .corpus import export_jsonl
    stats = export_jsonl(storage.all_records(), path)
    print(f"已导出 {stats['output']}/{stats['input']} 条规范化记录 -> {path}")
    print(f"去重：URL {stats['dropped_url']} 条，正文指纹 {stats['dropped_content']} 条")
    print(f"质检排除：失败/空白/导航薄页 {stats['rejected']} 条")
    return 0


def cmd_migrate(storage, db_path: str) -> int:
    """records -> documents 迁移（T1/T2：四表 schema + academic_year 下沉）。"""
    import sqlite3

    from .db import init_schema, migrate_from_records

    conn = sqlite3.connect(db_path)
    try:
        init_schema(conn)
        stats = migrate_from_records(storage.all_records(), conn)
    finally:
        conn.close()
    print(f"已建/更新四表 schema（schema.sql），迁移 {stats['documents']} 条文档 <- "
          f"records {stats['input']} 条")
    print(f"去重：URL {stats['dropped_url']} 条，正文指纹 {stats['dropped_content']} 条")
    return 0


def cmd_ask(config, question: str) -> int:
    """DeepSeek + web_search 工具的联网问答（function calling 循环）。"""
    from .agent import WebSearchAgent
    from .llm import DeepSeekClient, LLMConfig, LLMError
    from .websearch import build_searcher

    client = DeepSeekClient(LLMConfig.from_conf(config.get("llm")))
    searcher = build_searcher(config.get("websearch"))
    max_results = int((config.get("websearch") or {}).get("max_results", 5))
    agent = WebSearchAgent(client, searcher, max_results=max_results)
    try:
        result = agent.ask(question)
    except LLMError as exc:
        print(f"[FAIL] LLM 调用失败: {exc}")
        return 1
    print("=== 回答 ===")
    print(result.answer)
    print(f"\n（LLM 轮数={result.rounds}，搜索={result.queries or '无'}）")
    if result.sources:
        print("=== 来源 ===")
        for url in result.sources:
            print(f"  {url}")
    return 0


def main(argv=None) -> int:
    _fix_console_encoding()
    ap = argparse.ArgumentParser(description="CityU 学生服务 FAQ 采集器（agentic RAG 语料）")
    ap.add_argument("--config", default=cfg.DEFAULT_CONFIG)
    ap.add_argument("--db", metavar="PATH", help="覆盖配置中的 SQLite 路径")
    ap.add_argument("--import-corpus", metavar="JSONL", help="接收完整 JSONL 快照到 documents，不读取 records")
    ap.add_argument("--quality-source", choices=["records", "documents"], default="records",
                    help="明确质检输入：原始采集记录或活动文档快照")
    ap.add_argument("--quality-output", metavar="PATH", help="质检报告输出路径")
    ap.add_argument("--column", action="append", default=[], help="只抓指定栏目，可重复")
    ap.add_argument("--live", action="store_true", help="实际联网抓取；缺省为 dry-run")
    ap.add_argument("--full", action="store_true", help="种子优先全量补齐，已有链接不终止扫描")
    ap.add_argument("--dry-run", action="store_true", help="只打印抓取计划（缺省行为）")
    ap.add_argument("--mode", choices=["stealthy", "http", "fake"], default=None)
    ap.add_argument("--smoke", metavar="URL", help="只抓一页做连通性验证")
    ap.add_argument("--status", action="store_true", help="查看库内统计")
    ap.add_argument("--quality", action="store_true", help="核查全部种子与合格语料覆盖并保存 JSON 报告")
    ap.add_argument("--export", metavar="PATH", help="导出 JSONL 语料")
    ap.add_argument("--migrate", action="store_true",
                    help="records -> documents 迁移（建四表 schema + academic_year 下沉）")
    ap.add_argument("--min-date", default=None, help="只入库不早于该日期的内容（ISO）")
    ap.add_argument("--max-pages", type=int, default=None, help="覆盖各栏目的 max_pages（试跑用）")
    ap.add_argument("--repair-loops", type=int, default=1,
                    help="失败详情页的二次回放次数（默认 1，0 表示关闭）")
    ap.add_argument("--ask", metavar="QUESTION", help="DeepSeek + web_search 联网问答")
    args = ap.parse_args(argv)

    if args.import_corpus and any((args.live, args.migrate, args.export, args.smoke, args.ask, args.status, args.quality, args.column, args.mode)):
        ap.error("--import-corpus 是完整快照操作，不能与采集/迁移/导出/筛选操作同时使用")
    config = cfg.load_config(args.config)
    if args.ask:
        return cmd_ask(config, args.ask)
    columns = cfg.build_columns(config)
    if args.max_pages:
        for column in columns:
            column.max_pages = min(column.max_pages, args.max_pages)
    if args.column:
        wanted = set(args.column)
        columns = [c for c in columns if c.name in wanted]
        if not columns:
            print(f"未找到栏目: {sorted(wanted)}")
            return 1

    storage_conf = config.get("storage") or {}
    db_path = args.db or storage_conf.get("path", "data/cityu_faq.db")
    if args.mode == "fake":
        db_path = "data/demo_fake.db"   # 离线演示库，不污染真实语料库
    cfg.ensure_parent_dir(db_path)
    if args.import_corpus:
        import sqlite3
        from .corpus_import import import_corpus
        conn = sqlite3.connect(db_path)
        try:
            report = import_corpus(args.import_corpus, conn)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        except (ValueError, OSError, sqlite3.Error) as exc:
            print(f"[FAIL] 快照接收失败: {exc}")
            return 1
        finally:
            conn.close()
    storage = SQLiteStorage(db_path)
    try:
        if args.status:
            result = cmd_status(storage)
            import sqlite3
            from .db import init_schema
            conn = sqlite3.connect(db_path)
            try:
                init_schema(conn)
                counts = conn.execute("SELECT COUNT(*),SUM(active=1),SUM(active=1 AND index_dirty=1) FROM documents").fetchone()
                print(f"documents 总数={counts[0]} 活动={counts[1] or 0} 待建索引={counts[2] or 0}；records 为原始采集层")
            finally:
                conn.close()
            return result
        if args.quality:
            if args.quality_source == "documents":
                import sqlite3
                from .corpus_import import document_quality
                conn = sqlite3.connect(db_path)
                try:
                    report = document_quality(conn, columns)
                finally:
                    conn.close()
                failed = (report["integrity"] != ["ok"] or bool(report["foreign_key_errors"])
                          or bool(report["version_mismatch"]) or report["seed_success"] != len(report["seeds"]))
            else:
                from .corpus import quality_report
                report = quality_report(storage.all_records(), columns)
                report["source"] = "records"
                failed = report["seed_success"] != len(report["seeds"])
            output = args.quality_output or ("data/quality_documents.json" if args.quality_source == "documents" else "data/quality_report.json")
            cfg.ensure_parent_dir(output)
            with open(output, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return int(failed)
        if args.export:
            import sqlite3
            from .db import init_schema
            conn = sqlite3.connect(db_path)
            try:
                init_schema(conn)
                imported = conn.execute("SELECT 1 FROM corpus_imports LIMIT 1").fetchone()
            finally:
                conn.close()
            if imported:
                print("[FAIL] 本库接收了 JSONL 快照；--export 只处理 records，不能用它覆盖交付快照。请保留原 JSONL，并由成员②重新导出修正版。")
                return 1
            return cmd_export(storage, args.export)
        if args.migrate:
            try:
                return cmd_migrate(storage, db_path)
            except ValueError as exc:
                print(f"[FAIL] {exc}")
                return 1
        if args.smoke:
            politeness = config.get("politeness") or {}
            fetcher = build_fetcher(politeness, config.get("fetcher") or {}, mode=args.mode)
            return cmd_smoke(fetcher, args.smoke)
        if not args.live:
            return cmd_dry_run(columns, set(args.column))

        politeness = config.get("politeness") or {}
        limits = config.get("limits") or {}
        fake_pages = None
        if (args.mode or (config.get("fetcher") or {}).get("mode")) == "fake":
            from tests.mock_site import build_mock_column, build_mock_site  # 离线跑通流程用

            fake_pages = build_mock_site()
            if not args.column:
                print("[fake] 使用内置 mock 站点演示全流程（不联网）")
                columns = [build_mock_column()]
        fetcher = build_fetcher(politeness, config.get("fetcher") or {}, mode=args.mode,
                                fake_pages=fake_pages)
        crawler = DomainCrawler(
            columns, fetcher, storage,
            min_date=args.min_date,
            max_consecutive_404=int(limits.get("max_consecutive_404", 3)),
            min_content_len=int(limits.get("min_content_len", 300)),
        )
        results = crawler.crawl(repair_loops=max(0, args.repair_loops), full=args.full)
        print("=== 抓取完成 ===")
        for stats in results.values():
            print(stats.summary())
            for err in stats.errors[:5]:
                print(f"    ! {err}")
        fetch_stats = fetcher.stats
        print(f"\n请求={fetch_stats.requests} 挑战页={fetch_stats.challenges} 失败={fetch_stats.failures}")
        print(f"库中记录数={storage.count()}（db: {os.path.abspath(db_path)}）")
        return 0
    finally:
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
