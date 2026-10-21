"""CityU 学生服务 FAQ 采集器（agentic RAG 语料源）。

模块划分（对应 docs/Harness开发指导.md 的三件套）：
- storage.py  幂等写入 + 已存在查询（eval 依赖的接口）
- parser.py   HTML -> 结构化记录（清洗是抓取工作的一部分）
- fetcher.py  限速 + 重试 + WAF 挑战页检测 + 可替换适配器
- crawler.py  ColumnCrawler / DomainCrawler：列表页 + 详情页、栈式增量幂等
- config.py   config.yaml 读取
- main.py     CLI 入口
"""

__all__ = ["storage", "parser", "fetcher", "crawler", "config"]
