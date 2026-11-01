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

2026-10-31已授权发布`data/cityu_faq.db`脱敏副本及SHA一致的159行`data/corpus.jsonl`，文件版本见`data/release_manifest.json`。仅这两份数据和清单进入Git白名单；实际写入建议复制到忽略的`data/runtime.db`，更新基线前重新清理审计路径、检查隐私和文件SHA。公开基线不表示F项、政策规则或真实检索已验收。

③的有效读取入口：

```sql
SELECT url, title, source, content, topic, column_name AS "column",
       academic_year, date, crawled_at, image_urls, file_urls,
       corpus_sha256, index_dirty
FROM documents WHERE active = 1;
```

## 检索与应用查询契约（③源码已上传，⑤应用接入待验）

10/25远端`5282703`已提供`src/retriever.py`与`scripts/build_wsb_index.py`，源码实现基础切块、编码、索引构建和加载查询。11/01⑤已按用户授权补齐模型及构建条件，真实运行见下方N5接口；下游接收及质量验收另记。③的`Retriever`已含query编码和主题过滤，⑤复用该实现做别名、应用调用与Agent编排；④可按固定版本备测，不必等完整Agent。

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

# 以下为接口摘要；完整实现见远端src/retriever.py。
class Retriever:
    def __init__(self, index_dir: str = "data/wsb_index"): ...
    def search(self, query: str, topic: str | None = None, k: int = 5) -> list[Hit]: ...
    def list_topics(self) -> list[str]: ...
```

构建入口读本机`data/corpus.jsonl`，输出`data/wsb_index/index.faiss`及`chunks.json`，均组内传递，不公开提交。构建和首次查询均要求模型已在本机缓存（`local_files_only=True`）；检索依赖、模型准备、输入SHA及重建/加载说明须③补齐。下面的空结果、版本和失效要求是验收契约，不表示当前源码均已实现：现有加载主要检查向量/chunk数量；未校验语料SHA与模型revision，也未接active/dirty。

无命中返回空列表；模型/索引加载、维度或版本错误要可诊断，由⑤处理失败路径。Hit必须回溯文档和来源，不以FAISS行号冒充稳定chunk ID。上一轮对同SHA源码的合成检查发现FAQ首问前说明丢失、长单行突破字符上限，③须处理并按实际模型tokenizer核预算；本轮未重复运行。

保留既有约定，并标明当前源码与待验证要求；本轮不宣称真实模型验收通过：

1. 标题、段落、FAQ问答优先切块；费用/金额、日期/事项、开放时间/地点保持关联。500/80是历史token预算候选；现有源码按1500/200字符切块，不能当作相同token预算，须实际tokenizer核验。
2. 当前源码使用`intfloat/multilingual-e5-small`，文档加`passage: `、query加`query: `，两侧归一化；`BAAI/bge-m3`是历史1024维候选，不可混用其配置。③交实际维度/revision，⑤复用；当前全英文，不要求先做跨语言验收。
3. 小规模语料先考虑归一化向量＋`FAISS IndexFlatIP`；归一化须同时作用于文档和query。若增加HNSW或其他策略，说明课程承诺、实测收益与代价。
4. ③交付模型revision、维度、编码与归一化、切块配置、ID映射、字段取值、保存/加载/重建命令；⑤必须使用相同编码约定。
5. `fees`是column，topic为`学费与缴费`等标签；签证主文档在`admission`，不能把签证一律硬限于`visa_geo`。⑤维护明确的别名/候选映射。
6. 不能简单全库top-5再过滤并声称等价于合格候选内top-5。当前指定topic时先召回全量向量再过滤取k，不属于该截断漏检；小规模下可先验正确性，另报效率代价。④仍须测过滤边界。
7. 中文路径保存/重载须验证；既有实验中可用`serialize_index`配合Python文件读写与`deserialize_index`。
8. 索引绑定语料SHA和模型/构建版本；查询检查active和版本。清理失效chunk/索引后，确认期间来源未变化，才能清dirty。

<a id="n5-local-backend"></a>
## N5本地问答接口（2026-11-01真实检索候选）

⑤新增`src/local_rag.py`，复用③`Retriever`，固定一次Top-5；`mode="rag"`再执行一次LLM生成，`mode="retrieval"`只返回命中正文，不需要密钥。`src/local_sources.py`加载本机模型/索引、检查元数据，并提供可选的只读数据库检查；`src/local_demo.py`只用于合成接线演示。未实现N7动态路由、多跳、反思或完整四模式runner。旧Web `--ask`与新`--ask-local`互斥，绝不自动回退Web。

①界面、④⑥评测可以直接调用；后端对象可复用，`load_retriever`只在初始化时加载模型：

```python
from src.local_sources import load_retriever
from src.local_rag import LocalRAGBackend

def main():
    retriever, versions, warnings = load_retriever(
        "data/wsb_index", model_path="data/models/e5-small-614241f")
    try:
        backend = LocalRAGBackend(retriever, None,
            db_path="data/runtime_indexed.db", versions=versions, warnings=warnings)
        result = backend.ask("How can I pay my tuition?", mode="retrieval",
            topic="fees", case_id="dev-001").to_dict()
        print(result)
    finally:
        retriever._model.close()

if __name__ == "__main__":
    main()
```

真实加载前应捕获`LocalSourceError`，其`code/message`可直接给界面；不要展示异常原始cause或provider响应。省略`db_path`仅用于候选接入，结果会提示数据库未检查。模拟版可将依赖替换为`DemoRetriever()`和`DemoClient()`，实际生成不提供联网工具。

E5在持久子进程中运行，避免macOS上FAISS/PyTorch的OpenMP冲突；应用启动必须有上述`__main__`保护，不能在模块导入时启动模型。一个后端实例串行处理查询，并发请求由上层排队。要接真实生成，在本机配置密钥后用`DeepSeekClient(LLMConfig.from_conf(load_config().get("llm")))`替换`None`并指定`mode="rag"`；用户已在本机配置密钥并完成一次真实调用，记录见协作页。

| 输入 | 约定 |
|---|---|
| `question` | 非空英文问题，最多8000字符；当前不做自动语言检测或翻译 |
| `topic` | 可省略；支持真实topic或`admission/visa/visa_geo/registration/residence/fees/scholarship/library/calendar`别名。签证别名保持不筛主题，避免遗漏admission证据；这是显式别名适配，不是自动路由 |
| `persona/as_of` | 用户已知条件字典及参考日期；同时传入检索查询和生成上下文。输入JSON总长最多12000字符。不得夹带gold或预期动作 |
| `case_id` | 可选评测ID，只留结果，不传给模型 |
| `mode` | `rag`（默认）或`retrieval`；CLI分别为默认或`--retrieve-only` |

| 结果字段 | 含义与使用方式 |
|---|---|
| `mode/status/answer/case_id` | `rag`正常为`answered/clarify/abstained/no_evidence`；`retrieval`有命中返回`retrieved`，`answer`为空；故障答案保持空 |
| `citations/sources` | 引用含`source_id/chunk_id/doc_id/url/title`，只含实际使用来源；URL由检索元数据映射，不接受模型造URL。纯检索无生成引用，来源及正文在`retrieval_rounds[].hits` |
| `retrieval_rounds` | 首轮实际query、topic及完整有序Hit；不补位、不将无效Hit跳过后算另一个Top-5 |
| `context_chunk_ids/tool_calls` | 最终送生成的片段ID，以及本地检索调用；未生成时上下文ID为空 |
| `latency_ms/usage` | ask调用的总耗时，不含初始化加载；现有LLM client不提供usage，因此保持null |
| `versions/warnings/error` | prompt版本、生成/Embedding模型、已知索引文件SHA等；未知版本为null。调用方可传入实际Git commit；文件SHA、数据库SHA及索引语料绑定分别记录 |

可诊断错误包括`invalid_input/config_error/index_unavailable/model_unavailable/index_mismatch/database_unavailable/stale_evidence/source_mismatch/retrieval_error/context_limit/generation_error/invalid_response`。CLI正常结果退出0，以上错误退出1，参数冲突退出2。无命中直接返回`no_evidence`，不调用LLM；正文超出默认24000字符预算整次失败，不截掉政策条件。字符预算不等于模型token计量。

生成响应使用严格JSON：`answered`提供`statements[{text,source_ids}]`与空`message`；`clarify/abstained`提供空`statements`及非空`message`。程序为事实句加入`[S1]`等标记，并拒绝未知引用、无引用事实、模型生成的网址和错误结构。**这只验证引用来自上下文，不自动证明证据支持结论或确实适用**；⑥仍须按rubric复核。

真实取件与验收边界：

- 11/01用户授权从真实发布语料补建开发候选；`scripts/download_e5`固定官方revision，`scripts.prepare_local_index`复用③切块且不改发布库。模型、语料、输入库、索引文件与构建源码SHA写入`chunks.json`，加载时核验文件及模型。旧格式仍兼容并明确提示版本缺失，不能把旧格式推断为已绑定。
- 显式指定数据库时，对首轮每条证据检查`documents.active=1/index_dirty=0`及一致的快照身份。发现一条失效即停止，不修改数据库。`database_corpus_sha256`是查到的数据库身份，不能冒充`corpus_sha256`（索引输入身份）。
- 新候选在编码成功后向独立`runtime_indexed.db`写881个片段，仅清除157篇有片段文档的dirty状态；另2篇仍dirty。查询逐条核对数据库片段的doc_id及正文，防止只看标志误用错版。原③切块缺陷未修复，不以该候选替代正式N3接受。
- 11/01固定E5 revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`，真实FAISS/E5建库、5次各Top-5及真实CLI运行成功；全仓库104项测试通过。具体SHA、遗漏文档、相关性失败及命令在协作页。随后用户完成一次`deepseek-flash`真实调用，返回`answered`，5条命中与数据库一致、S3引用映射及回答事实支持检查通过。未做正式20题评分或下游签收；10/31的98项为历史模拟证据。
- Git交代码、测试与此接口文档；真实证据和trace留`runs/`。N5可交①接界面、④⑥做接口联调；正式通过仍由接收者确认。N6/N7不因这些测试变为通过。

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

## 2026-11-01 成员6固定测试材料

按⑤明确授权，取件分支包含`data/wsb_index/index.faiss`、`chunks.json`和无日志的`data/runtime_indexed.db`，不需要⑥重建。运行`python -m scripts.verify_local_assets`检查原始发布文件SHA、索引SHA、模型每个文件SHA、全部运行库片段和dirty状态；尚未下载模型时可用`--skip-model`仅检查数据链路材料。实际加载/查询继续使用上方接口，Windows通过`python -m`入口启动以保证spawn保护。模型LFS尚未上传时先运行`python -m scripts.download_e5`，README给出完整开测步骤；不得声称只拉Git就已拿到权重。
