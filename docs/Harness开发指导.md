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

⑤新增`src/local_rag.py`，复用③`Retriever`，固定一次Top-5；`mode="rag"`再执行一次LLM生成，`mode="retrieval"`只返回命中正文，不需要密钥。`src/local_sources.py`加载本机模型/索引、检查元数据，并提供可选的只读数据库检查；`src/local_demo.py`只用于合成接线演示。11/18新增独立N7后端，见下节；完整四模式批量runner尚未实现。旧Web `--ask`与新`--ask-local`互斥，绝不自动回退Web。

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
| `latency_ms/usage` | ask调用的总耗时，不含初始化加载；N5仍使用message-only接口，usage保持null。N7通过新增per-call元数据接口记录实际usage |
| `versions/warnings/error` | prompt版本、生成/Embedding模型、已知索引文件SHA等；未知版本为null。调用方可传入实际Git commit；文件SHA、数据库SHA及索引语料绑定分别记录 |

可诊断错误包括`invalid_input/config_error/index_unavailable/model_unavailable/index_mismatch/database_unavailable/stale_evidence/source_mismatch/retrieval_error/context_limit/generation_error/invalid_response`。CLI正常结果退出0，以上错误退出1，参数冲突退出2。无命中直接返回`no_evidence`，不调用LLM；正文超出默认24000字符预算整次失败，不截掉政策条件。字符预算不等于模型token计量。

生成响应使用严格JSON：`answered`提供`statements[{text,source_ids}]`与空`message`；`clarify/abstained`提供空`statements`及非空`message`。程序为事实句加入`[S1]`等标记，并拒绝未知引用、无引用事实、模型生成的网址和错误结构。**这只验证引用来自上下文，不自动证明证据支持结论或确实适用**；⑥仍须按rubric复核。

真实取件与验收边界：

- 11/01用户授权从真实发布语料补建开发候选；`scripts/download_e5`固定官方revision，`scripts.prepare_local_index`复用③切块且不改发布库。模型、语料、输入库、索引文件与构建源码SHA写入`chunks.json`，加载时核验文件及模型。旧格式仍兼容并明确提示版本缺失，不能把旧格式推断为已绑定。
- 显式指定数据库时，对首轮每条证据检查`documents.active=1/index_dirty=0`及一致的快照身份。发现一条失效即停止，不修改数据库。`database_corpus_sha256`是查到的数据库身份，不能冒充`corpus_sha256`（索引输入身份）。
- 新候选在编码成功后向独立`runtime_indexed.db`写881个片段，仅清除157篇有片段文档的dirty状态；另2篇仍dirty。查询逐条核对数据库片段的doc_id及正文，防止只看标志误用错版。原③切块缺陷未修复，不以该候选替代正式N3接受。
- 11/01固定E5 revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`，真实FAISS/E5建库、5次各Top-5及真实CLI运行成功；全仓库104项测试通过。具体SHA、遗漏文档、相关性失败及命令在协作页。随后用户完成一次`deepseek-flash`真实调用，返回`answered`，5条命中与数据库一致、S3引用映射及回答事实支持检查通过。未做正式20题评分或下游签收；10/31的98项为历史模拟证据。
- Git交代码、测试与此接口文档；真实证据和trace留`runs/`。N5可交①接界面、④⑥做接口联调；正式通过仍由接收者确认。N6/N7不因这些测试变为通过。

<a id="n7-agentic-backend"></a>
## N7动态本地编排（2026-11-18开发候选）

N5已完成；N7新增`src/agentic_rag.py`的`AgenticRAGBackend`，复用N5检索与数据库核验，不修改切块、query编码或发布数据。默认检索配置仍是E5-only，没有自动接入韩上的rerank；17/20的候选指标不能移植到本模式。主题选择发生在检索器内部过滤之前，不是全库Top-5后过滤。签证别名保持跨主题；模型可以选择已有topic/别名或null放宽范围，不接受未知主题。

```python
from src.agentic_rag import AgentBudget, AgenticRAGBackend
from src.config import load_config
from src.llm import DeepSeekClient, LLMConfig
from src.local_sources import load_retriever

def main():
    retriever, versions, warnings = load_retriever(
        "data/wsb_index", model_path="data/models/e5-small-614241f")
    try:
        backend = AgenticRAGBackend(
            retriever, DeepSeekClient(LLMConfig.from_conf(load_config().get("llm"))),
            db_path="data/runtime_indexed.db", versions=versions, warnings=warnings,
            budget=AgentBudget(max_retrieval_rounds=3, max_llm_calls=4,
                               max_context_chars=24000, max_elapsed_s=90))
        result = backend.ask("What payment methods are available for tuition fees?",
                             case_id="dev-001", persona={}, as_of="2026-11-18")
        print(result.to_dict())
        # 若result.status == "clarify"，界面收取真实用户回答后再次调用：
        # backend.ask(原问题, persona=原已知条件, as_of=原参考日期,
        #             clarification=用户补充, case_id=原ID)
    finally:
        retriever._model.close()

if __name__ == "__main__":
    main()
```

每次ask独立计预算，不保存隐藏会话状态，不信任调用者传回的旧证据。澄清补充通过`clarification`和原问题重新检索、核验；用户等待时间不计入处理预算。上层应限制连续澄清次数；后端不伪造用户回答。`question/topic/case_id/persona/as_of`沿用N5契约；`clarification`为可选非空字符串，与其他输入合计最多12000字符。当前不实现语言检测/翻译。`case_id`不进入提示词，模型只得到问题、已知条件、实际证据及预算，不接收金标、预期动作或评分。

动作契约为严格JSON，样例见源码`AGENT_PROMPT`：`retrieve/answer/clarify/abstain`必须提供简短`reason`及`missing_information`。补检索另带`query/topic`；终态另带与N5相同的`response{status,statements,message}`。`answer`必须没有未解决缺口；其他动作必须指出缺什么。程序验证动作结构、引用身份和预算，**证据充分性、冲突是否解决、澄清是否必要仍是模型判断，须⑥独立评分**。reason只是操作说明，不采集或要求完整思维链。

首轮固定一次Top-5；之后模型围绕缺口改写查询、调整主题或拆子问题。所有轮次保留实际顺序的Top-5，累计证据按chunk_id去重并赋稳定S1、S2等ID。同一chunk跨轮正文或身份变化则失败；每轮逐条复用N5的active/dirty、来源版本及片段正文检查，终态发布前再次检查全部累计证据。无效证据不跳过、不补位；本地文件或数据库错误保留失败状态，不伪装为正常拒答。

| 新增输出 | 含义 |
|---|---|
| `mode` | `agentic_rag`；N5继续使用`rag/retrieval` |
| `decisions` | 实际通过结构校验的动作、短理由、缺口及补检索参数；请求过但被预算拒绝的动作不冒充已执行工具 |
| `stop_reason` | 见下表；`status`仍区分answered、clarify、abstained及错误 |
| `budget.limits/used` | 配置上限、已尝试检索轮数、LLM调用次数和当前累计证据正文字符数；不把字符数当token |
| `retrieval_rounds` | 各轮实际query/topic/有序hits；首轮结果始终独立保留 |
| `context_chunk_ids` | 最近一次实际送入模型的累计片段ID；尚未调用模型时为空。每次模型调用另在tool_calls中记录当次上下文ID |
| `citations/sources` | 最终实际引用；可跨轮，必须属于送入模型的证据；程序映射URL，拒绝生成的网址或未知ID |
| `tool_calls/usage` | 实际检索与模型调用、状态、每次模型调用实际usage。仅所有模型调用usage齐全且合法时汇总，否则总usage=null，不估造费用 |
| `answer_reviews` | v2候选答案发布前的单独检查：原问题各项需求是否被覆盖、无依据断言序号、缺口及短理由；不是正式评分 |
| `versions` | 当前prompt=`n7-local-agentic-v2`、answer_review_prompt=`n7-answer-review-v1`，沿用数据/模型/索引版本；调用者可提供实际git_commit，未知值仍为null |

| `stop_reason` | 状态与行为 |
|---|---|
| `evidence_sufficient` | answered，严格解码事实句及引用后发布 |
| `needs_clarification` | clarify，向用户提出聚焦问题，无政策断言及伪引用 |
| `insufficient_evidence` | abstained，模型说明缺口与下一步 |
| `answer_incomplete/answer_unsupported` | abstained，最终检查发现漏答原问题的一部分或存在无依据断言，候选答案及其引用不发布 |
| `repeated_query` | abstained，query忽略大小写/空白且topic解析后与已执行查询相同，不再次搜索 |
| `no_new_evidence` | abstained，补检索没有新增chunk，不再追加模型调用；首轮空结果仍可请求改写 |
| `retrieval_budget/llm_budget/time_budget` | abstained，到预算即停止，无强制收尾调用，不发布超时返回的答案 |
| `context_budget` | context_limit，完整证据超出字符预算，保留原始命中、不截掉条件 |
| 与错误状态同名 | invalid_input、retrieval_error、source_mismatch、stale_evidence、generation_error、invalid_response等，error给脱敏诊断，answer为空 |

CLI为`--ask-local QUESTION --local-mode agentic_rag`；支持`--persona JSON --as-of DATE --clarification TEXT`及`--agent-max-rounds/--agent-max-llm-calls/--agent-context-chars/--agent-timeout-s`。`--retrieve-only`与agentic_rag互斥；预算/澄清选项只能用于agentic_rag，参数错误退出2；正常终态含预算拒答退出0，工程错误退出1。`--rag-demo`运行两轮合成fixture，无网络、模型或学校制度断言。

90秒是ask处理预算，不含初始化。每次同步工具调用前后检查期限；DeepSeek单次HTTP timeout取配置与剩余预算的较小值。自定义同步Retriever/client不能被强制中断，E5现有worker也有自己的等待期限，故不承诺所有在途调用的严格90秒墙钟上限；超期结果不会发布。默认最多3轮检索、通常至多3次决策；v2的单独最终检查也计入原有4次LLM上限，因此3轮决策加1次检查恰为4次。检查没有剩余调用或时间预算时直接停止，不发布未检查的草稿。生成单次max_tokens沿用配置；累计usage未知时不声称已实施总token硬预算。

11/18首次验证：`python -m unittest discover -s tests -q`共139项通过，其中35项新增N7/CLI/LLM元数据测试；两轮合成演示通过。当时`python -m scripts.verify_local_assets --skip-model`退出0，159篇/157篇已索引/881片段，`model_checked=false`，尚未取得E5缓存及密钥。该历史检查不证明语义、效果或N7正式通过。

同日按用户授权完成环境准备：固定检索依赖安装完成，`python -m pip check`退出0；从官方来源取得E5固定revision的11个文件，全部核对原构建SHA256。网络中断后采用断点/分段下载，PyTorch/Transformers/SciPy安装包另按PyPI官方SHA256核验，未修改依赖版本、语料、索引或数据库。`python -m scripts.verify_local_assets`退出0，`status=verified/model_checked=true`、159篇/157篇已索引/881片段。通过`load_retriever`实际加载E5子进程，并编码一条合成环境检查文本：形状1×384、数值有限且归一化、模型最大序列长度512；未调用Retriever.search或回答生成。依赖安装后139项测试仍全部通过。

本机使用被Git忽略、权限0600的`config.local.yaml`保存个人LLM配置，`api_key`与`api_key_env`分别表示实际密钥及环境变量名，不能互换。后续命令增加`--config config.local.yaml`；环境准备阶段仅验证API模型列表认证成功、所配`deepseek-flash`可见，当时未发起回答生成。密钥与原始准备记录只留忽略目录，不写入共享文档、Git或trace；随后首份真实回答见下一段，DEV调试及正式评分仍待后续。

同日随后取得首份真实N7输出：问题为`What payment methods are available for tuition fees?`，实际命令为`python -m src.main --ask-local "What payment methods are available for tuition fees?" --local-mode agentic_rag --config config.local.yaml --model-path data/models/e5-small-614241f --index-dir data/wsb_index --db data/runtime_indexed.db --json`。受限环境首次退出1、`generation_error`，记录在`runs/n7-real-20261118/attempt_01.json`；联网重试退出0，原始成功输出为同目录`first_output.json`。返回`mode=agentic_rag/status=answered/error=null/stop_reason=evidence_sufficient`，1轮Top-5、1次LLM调用、累计正文5633字符；usage为prompt 2913、completion 314、total 3227，ask耗时4488ms（不含加载）。没有调用Web工具或改写问题。

逐条再次核验5条命中的active/dirty、语料身份、chunk正文及数据库绑定均通过；最终S4指向第四条命中`https://www.cityu.edu.hk/fo/htm/paymethods.htm#chunk-1`，六项断言中的支付渠道、到账说明及家长/资助者代付均可在该片段找到依据。此为开发侧快照支持检查，不证明政策现行性、回答完整性或⑥正式评分。该题与此前N5开发问题相同，首轮证据已足够，真实多轮补检索、澄清及预算边界尚未由此单题验证。原输出保留`versions.git_commit=null`；同目录忽略的`run_manifest.json`绑定实际基线提交、dirty工作区源码SHA、脱敏配置和运行包版本，未用基线SHA冒充新增代码已提交。正式验收与题集分工不变。

受影响节点：N7新增后端；①可按stop_reason展示停止/澄清，④分别统计首轮Top-5、累计证据、调用及耗时，⑥评估动作、条件和断言—引用支持。N5行为保留作单轮基线。N6正式达标、同版真实运行及④⑥评分/接收仍需补齐；原公开CORE20可作回归，不再作为未见留出测试集。完整四模式批量runner、rerank集成及界面属于后续独立工作，不因本候选自动完成。

### 11/19真实DEV与v2发布检查

本轮全部是⑤编写的DEV场景，不是④⑥冻结金标。v1留档展示真实3轮检索（ORCID与家长代付）、借阅条件澄清及补充后再检索、私人付款状态/实验室信息缺失拒答；低LLM预算真实触发`llm_budget`。仅有1ms预算的场景使用真实E5且未请求LLM，返回`time_budget`，实际耗时可超过1ms，因为在途同步检索不能强行中断。检索轮数、无新增证据、重复查询另有明确标记的动作回放/命中冻结控制，不能冒充新的真实模型决策。初次低预算题本来首轮证据充分，未触及硬拦截，后续改用已触发多轮的题补验；全部输出均保留。

v1补充案例暴露实质缺陷：模型承认ORCID信息仍未覆盖，却只回答家长代付并将missing_information置空，最终误标`answered/evidence_sufficient`。原始失败在`runs/n7-dev-20261119/N7-DEV-MULTI-003.json`；另一道ORCID定义题侧重用途，定义完整性亦保留为待复核项，未算作完整回答通过。

v2在所有answered候选发布前增加独立请求，输入仅为原问题/用户条件、候选事实句和实际证据，不把先前决策理由、DEV预期动作或金标传给检查器。输出严格为`verdict/requirements/unsupported_statements/missing_information/reason`；每项需求有request和covered，unsupported_statements为1起的事实句序号。accept须全部需求covered且无缺口/无依据断言；incomplete须有未覆盖需求及缺口；unsupported须列出无依据断言及缺口。结构矛盾、坏引用、检查失败或超预算均不发布草稿。单独检查和决策通过同一计数/耗时/usage入口，工具名分别为`agent_decision`和`answer_review`，最终再次核验数据库有效性。

复测学费支付问题v2实际3轮检索、3次决策加1次检查后answered，ask耗时21853ms，usage=25046+972=26018，引用S11/S12/S13分别对应付款方式页chunk-1/2/5。ORCID与代付的原回归题分别因证据缺失或重复查询停止，没有继续默默漏答；借阅条件补充后仍查不到授课型硕士具体配额/期限，正确保留拒答而不杜撰。对保存的v1坏草稿发起一次真实检查，返回incomplete；完整动作/证据/检查结果回放在程序内得到`abstained/answer_incomplete`，该回放没有新API请求。

共留档19次ask场景（含两个真实E5短时限注入、预算变体和澄清后续轮，不是19个独立问题），32次实际API请求，另1次对旧草稿的真实检查；4个停止回放及1个漏答拦截回放另记且不计API流量。详细输出、各次模型输入/响应、v1/v2源码SHA及`verification_summary.json`在本机忽略目录`runs/n7-dev-20261119/`，没有把失败输出剔除。逐轮命中通过数据库片段正文/版本核对，引用ID及累计上下文、实际调用/usage与预算均核对通过；144项离线回归通过，含5项新增完整性/支持/检查失败/检查超时/检查预算回归。资料及索引未修改，N5单轮行为保留。

该检查器仍使用同一生成模型，不能视为独立人工评分或保证完整性永远正确。检索覆盖、定义信息缺口、语料现行性、无引用拒答中具体导航/转介建议及最终事实支持仍需⑥复核；未登记正式Hit@5、任务成功率或N7验收。v2多一次检查的开销已计入调用数、usage与耗时，不能与历史v1单题数字直接声称公平性能改善。

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
