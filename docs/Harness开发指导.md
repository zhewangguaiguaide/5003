# 开发与接口约定

本页汇总保留下来的运行约束与检索决定。当前职责和验收以[需求节点](协作与需求节点.md)为准；实际入口以`src/main.py --help`、`src/corpus_import.py`和`schema.sql`为准。现有采集/接收代码与拟议检索接口分开说明。

## 已实现的运行链路

`config.yaml → fetcher → parser → crawler → records → 清洗导出JSONL`；`完整JSONL → corpus_import → documents`。`agent.py/llm.py/websearch.py`是独立的联网搜索雏形，尚未连接自有文档检索。

| 模块 | 职责与维护点 |
|---|---|
| `fetcher.py` | fake/http/stealthy适配、限速与重试；挑战页检测结合长度和标记，不能只凭WAF脚本标记误判 |
| `parser.py`、`corpus.py` | 标题/正文/附件解析、URL与正文去重、薄页及学年处理；②F1/F2待闭环 |
| `crawler.py` | 列表/详情、LIFO、增量幂等、全量种子优先与失败回放；成功URL与失败记录要区分 |
| `storage.py` | 原始`records`；`exists/upsert/count/all_records`是测试与采集契约 |
| `db.py`、`schema.sql` | 规范化表、旧库升级、审计及引用保护；路径随根目录搬迁保持相对定位 |
| `corpus_import.py` | 完整快照先校验后事务接收，不重新推断②字段语义 |
| `main.py` | CLI；fake会导入`tests/mock_site.py`，因此发布运行集合必须保留该模块 |

抓取按配置限速2–3秒，限定服务页范围；失败原因保留，修复用失败与成功样例一起回归。浏览器需另装依赖与资源，F3的真实验证不能用fake通过替代。日期可能回落为抓取时间，不能直接当政策生效日期。

## 完整快照与存储契约（已实现）

JSONL每行恰好12字段，不能擅自增删；完整快照不能用差异片段代替。

| 字段 | 类型与含义 |
|---|---|
| `url`、`title`、`source`、`content` | 字符串；url规范化且为绝对HTTP(S)，正文非空 |
| `date`、`crawled_at`、`academic_year` | 字符串；学年不明确可空，输入语义由②负责 |
| `topic`、`column`、`error` | 字符串；交付error必须为空；topic是标签，column是配置栏目 |
| `image_urls`、`file_urls` | 字符串数组；数据库保存为JSON文本，读取时解析 |

接收拒绝空快照、重复URL、重复规范化正文、失败和字段错误；导入原样保留合法字段，不把“相邻年份”自动视为正确学年。来源SHA按原文件字节计算。

- `records`保留采集原始层；正式检索读`documents.active=1`，不混读旧records。
- `column`入库为`column_name`，文档URL是`documents`主键及`chunks.doc_id`关联目标。
- 快照新增或元数据/正文变化使`index_dirty=1`；删除文档若仍被chunk引用则保留为inactive，不能从旧索引继续返回。
- `crawl_runs`是抓取审计，`corpus_imports`是接收审计，`qa_logs`是回答留痕；用途不同。
- 已接收JSONL的库禁止用旧`--migrate/--export`覆盖；重新同步用`--import-corpus`。
- 导入报告的`semantic_review=pending_member2`和`release_ready=false`不是程序故障；程序没有替②完成语义验收。

③的有效读取入口：

```sql
SELECT url, title, source, content, topic, column_name AS "column",
       academic_year, date, crawled_at, image_urls, file_urls,
       corpus_sha256, index_dirty
FROM documents WHERE active = 1;
```

## 检索与应用查询契约（待③⑤落地）

以下是对外约定，当前仓库没有可用的`src/retriever.py`。③负责切块/向量/索引/映射与基础加载检索，⑤负责query编码/调用、别名与应用编排；双方共同落实对外接口及过滤语义。

```python
@dataclass
class Hit:
    chunk_id: str
    doc_id: str        # documents.url
    text: str
    score: float
    url: str
    title: str
    topic: str
    academic_year: str

# 拟议调用面，③⑤实现时对齐；不是当前可导入的运行代码。
def search(query: str, topic: str | None = None, k: int = 5) -> list[Hit]: ...
def list_topics() -> list[str]: ...
```

无命中返回空列表；模型/索引加载、维度或版本错误要可诊断，由⑤处理失败路径。Hit必须回溯文档和来源，不以FAISS行号冒充稳定chunk ID。

沿用既有技术候选，本轮只整合，不宣称新一轮选型或模型验证：

1. 标题、段落、FAQ问答优先切块；费用/金额、日期/事项、开放时间/地点保持关联。500/80仅作初始对照，真实tokenizer需重算标题及特殊token预算。
2. `BAAI/bge-m3`是既有1024维候选；当前全英文，不要求以跨语言验收才能交付。模型未实际运行时不可声称已验证。
3. 小规模语料先考虑归一化向量＋`FAISS IndexFlatIP`；归一化须同时作用于文档和query。若增加HNSW或其他策略，说明课程承诺、实测收益与代价。
4. ③交付模型revision、维度、编码与归一化、切块配置、ID映射、字段取值、保存/加载/重建命令；⑤必须使用相同编码约定。
5. `fees`是column，topic为`学费与缴费`等标签；签证主文档在`admission`，不能把签证一律硬限于`visa_geo`。⑤维护明确的别名/候选映射。
6. 不能简单全库top-5再过滤并声称等价于合格候选内top-5。采用预过滤或可验证的扩大召回策略，并让④测试漏检。
7. 中文路径保存/重载须验证；既有实验中可用`serialize_index`配合Python文件读写与`deserialize_index`。
8. 索引绑定语料SHA和模型/构建版本；查询检查active和版本。清理失效chunk/索引后，确认期间来源未变化，才能清dirty。

## 历史小实验保留的结论

2026-10-17在159篇快照上以正则词/标点代理计数、1024维TF-IDF控制向量运行；**没有BGE-M3 tokenizer或模型推理**。14个开发探针不是独立验收集，延迟只算索引搜索，不含query编码和应用开销。

| 对照 | 块数 | 关键片段完整保留 |
|---|---:|---:|
| 固定300/40 | 695 | 13/14 |
| 固定500/0 | 410 | 13/14 |
| 固定500/80 | 447 | 14/14 |
| 固定800/80 | 310 | 14/14 |
| 结构V1 | 435 | 13/14 |
| 结构V2，绑定申请期与日期 | 435 | 14/14 |

V2依该开发失败修规则，不证明泛化最优。Flat与HNSW在这组词法控制查询结果一致，不能推出语义模型等效。内存生命周期实验发现inactive文档可保留旧chunk，说明查询过滤与索引同步必须实现；没有修改生产数据。

完整历史脚本与脱敏统计在提交`7f1d43b`的`检索层小实验_2026-10-17/`；当前目录不保留实验中间产物。真实模型、实际token预算及正式20题指标由③④⑤后续验证。

## 验证与提交

运行命令见[README](../README.md)。修改采集/导出规则时保留已成功样例，补有意义的边界回归；移动入口后检查配置、schema和fake流程。纯文档变更无需重跑真实抓取或模型实验。

③④⑤⑥交付时同时记录Git提交、数据SHA、模型/索引构建版本和题集配置；报告不能混入另一版本结果。详细日志放忽略的`runs/`，节点状态和脱敏摘要按[Git交接约定](协作与需求节点.md)维护。
