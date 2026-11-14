# 检索、LLM、RAG与Agentic RAG评测启动

更新：2026-10-26。先读[制度知识库研究与规则流程](../knowledge/README.md)，确定原文、适用范围和版本，再做真实证据标注。本目录不再提供独立合成知识库或合成DEV题集。当前没有已冻结的真实golden或四模式性能结果。

## 知识库、golden与rubric分开

| 材料 | 内容与位置 | 模型能否取得 |
|---|---|---|
| 原文知识库 | 当前159条`data/corpus.jsonl`及脱敏数据库已随Git发布，版本见`data/release_manifest.json`；新附件及索引仍由对应岗位交付 | RAG/Agent可以检索正文；当前基线的版本一致性已核，政策语义接受、覆盖缺口及正式索引另外核实 |
| 规则与流程目录 | `knowledge/catalog.json`及其生成视图；候选数量及证据状态见[知识入口](../knowledge/README.md)，尚未人工批准 | 只有与获准原文快照绑定、复核过的规则才可进入检索视图；候选目录不能整包索引 |
| golden题集 | ④⑥制作的`evals/private/dev.jsonl`、`core.jsonl`；含问题、必要事实、证据与预期动作 | 只发送题目与用户已知条件；标准答案、证据标签、预期动作与评分结果留评测侧 |
| rubric | `rubric.json`；通用分档、权重、阻断条件；⑥主责、④复核 | 用于人工或评测器，不作为学校制度、用户问题或检索正文 |

规则表不是golden。golden应根据原文独立核实；来源可以和知识库相同，但题目/标准答案不能混进知识库。知识库增加人工整理规则时，普通RAG与Agentic RAG共享同一版本，另报整理前后的收益。

## 四种模式与职责

| 模式 | 系统能力 | ④统计 | ⑥核对 |
|---|---|---|---|
| retrieval | 直接调用③的`Retriever.search(query, topic=None, k=5)` | 首轮Hit@5、事实证据覆盖、完整证据覆盖、耗时 | 证据是否支持必要事实；没有生成答案可评 |
| llm | 同一LLM直接回答，无知识库、检索及联网工具 | 内容正确性、任务结果、耗时和usage | 回答、澄清、越界行为；无检索上下文时忠实度N/A |
| rag | ⑤实现固定一次本地Top-5→同一LLM回答并引用 | 与其他模式成对比较 | 条件与例外、事实、引用及误拒答 |
| agentic_rag | ⑤允许动态选检索、补条件/补证据，并有停止与预算 | 收益、轮次、总token、耗时、成功任务成本 | 是否补齐缺口、合理停止、引用与异常行为 |

③的检索模块不是完整RAG。当前`--ask`是独立Web Agent；本地四模式runner仍待⑤实现，④负责实验与统计，⑥负责回答/引用评分。联网模式单列Web，不能把额外外部知识收益全算给Agent编排。

## 真实证据标注的最小启动流程

1. **冻结研究输入**：①确认接收的文件及SHA，②复核缺页、身份、届别、学年、例外与附件正文。来源只有索引或政策冲突未解决时，可以出题草稿，不能冻结事实。
2. **先选证据再出题**：④从已有答案的原文选5道DEV校准，优先覆盖学籍、费用、住宿、借阅和日期等真实目标。先做小组已约定的英文路线。官网有但语料没有是覆盖缺口，不强列为可回答。
3. **④标应该检到什么**：保存URL、原文小标题/段落、最短充分摘录、事实ID与可接受证据组合。相同URL不代表chunk相关；跨段证据分条存，不拼造原文句子。
4. **⑥标应该答什么**：必要事实、身份/届别/学年、预期回答/澄清/转介及禁止结论；金额连币种与收费口径，日期连事项、学年及暂定标记。无答案题不编造事实。
5. **交叉复核**：④⑥各自读原文，记录分歧与裁决，不能只读对方摘要或让模型自造金标再自评分。来源更新时复核受影响题目，不沿用旧结果。
6. **校准后另做CORE20**：开发与正式题按同源事实/意图分组隔离。CORE至少20道语料内可回答、检索适用题；澄清、个人状态、冲突与故障题另外加入。针对TEST修复后属于回归，泛化另用未见题。

题集仍用已有校验契约；当前未创建真实题集文件：

| 字段 | 填写要求 |
|---|---|
| `id/split/query/persona/as_of` | 唯一ID、`dev`或`test`、英文题干、用户已知条件、评测参考日期；不要把隐藏答案放入persona |
| `synthetic/review_status/gold_version` | 真实题`synthetic=false`；起草为`draft`；核实后才`frozen`；记录版本 |
| `answerability/expected_action` | 当前支持`answerable→answer`、`clarify→clarify`、`unanswerable→abstain/refer` |
| `required_facts` | 列表；每项`id/text/critical`；关键条件作为必要事实保留 |
| `gold_evidence` | 列表；每项`id/doc_id/locator/quote/fact_ids`；doc_id用快照URL，quote须是连续原文 |
| `sufficient_evidence_sets` | 证据ID组合列表；每个组合覆盖所有必要事实，允许不同等价组合 |
| `required_clarifications/forbidden_claims` | 需补条件与禁止结论列表；不能传入被测系统 |
| `retrieval_applicable` | 正向可回答题true；澄清、个人状态等不挤入正向检索分母 |
| `corpus_sha256/human_reviewed/reviewer_roles` | 绑定原始文件字节；真实审核后才true，冻结题至少记录`role4`和`role6` |

休学/退学等部分可回答、冲突或多轮场景先保留draft。扩展字段与校验后再冻结，不硬塞到不合适的三类标签。

## 候选ID分配与共用前检查

| ID命名空间 | 当前用途 | 共用规则 |
|---|---|---|
| `YP-DEV-001..008` | ⑥候选题集；其中正向DEV、行为场景分开管理 | 不重编号给④；共用前按语义意图映射并自行核对 |
| `YP-DEV-009..010` | ⑥评分校准与故障/超时校准设计 | 不计入正向检索分母 |
| `R4-DEV-001..005` | ④侧5道正向校准DEV | 只用于④证据与实验校准；不冒充⑥的`YP-DEV` |
| `CORE-*` | ④侧20道独立正向检索题 | 与行为、澄清、无答案和故障题分表 |

2026-11-04审计：当前`R4-DEV-*`与`CORE-*`没有重复ID、重复query、重复必要事实文本或重复`doc_id+quote`；“`YP-DEV-*`”只作⑥命名空间保留，当前私有④题集未占用。正式CORE不是DEV换问法，20题均有独立事实与原文证据。

④主做证据定位、检索指标和实验运行；⑥主做事实、动作、禁止结论和引用评分。`required_facts`、`expected_action`和`forbidden_claims`在独立复核前仍是候选字段，不得填造`reviewer_roles`、`human_reviewed=true`或`frozen`。N2同版只说明输入身份一致，不代表所有政策适用性已接受；研究目录中的额外私有原文须另行取得。复杂冲突或部分可回答场景保留draft，不强行塞进当前三类answerability。

## 校验与无gold输入导出

先自行完成真实DEV，以下文件必须实际存在：

```powershell
python -m scripts.check_eval_assets --corpus data/corpus.jsonl --cases evals/private/dev.jsonl
python -m scripts.check_eval_assets --corpus data/corpus.jsonl --cases evals/private/dev.jsonl --export-inputs runs/startup/dev_inputs.jsonl
python -m scripts.check_eval_assets --corpus data/corpus.jsonl --cases evals/private/core.jsonl --require-frozen --min-answerable 20
```

工具检查结构、语料SHA、原文摘录、事实/证据引用、充分集合、rubric权重及审核标记，不证明语义正确或审核已实际发生。SHA按文件原始字节计算；换行或重新格式化后需重算并复核，不能填造SHA。

导出只含`case_id`及`input.query/persona/as_of`；ID是评测元数据，不必进入提示词。输出限制在本仓库`runs/`并拒绝覆盖。字段白名单不能替代对persona的人工检查。

## 检索评测 runner

`scripts/evaluate_wsb.py` 已提供首版检索评测接口。它只接受 `answerable` 且
`retrieval_applicable=true` 的题目，调用
`Retriever.search(query, topic=None, k=5)`，并按返回 chunk 中是否实际包含
连续原文摘录匹配证据；同 URL 但没有摘录命中不算 Hit。

```bash
python -m scripts.evaluate_wsb \
  --corpus data/corpus.jsonl \
  --cases evals/private/core.jsonl \
  --index-dir data/wsb_index \
  --model-path data/models/e5-small-614241f \
  --output runs/retrieval/core20_results.jsonl \
  --summary runs/retrieval/core20_summary.json \
  --k 5
```

固定本地 rerank 模型并做候选深度消融时：

```bash
python -m scripts.evaluate_wsb \
  --corpus data/corpus.jsonl \
  --cases evals/private/core.jsonl \
  --index-dir data/wsb_index \
  --model-path data/models/e5-small-614241f \
  --rerank \
  --rerank-model-path data/models/mmarco-mMiniLMv2-L12-H384-v1-1427fd65 \
  --candidate-k 50 \
  --output runs/retrieval/core20_rerank50_results.jsonl \
  --summary runs/retrieval/core20_rerank50_summary.json \
  --k 5
```

逐题 JSONL 保留首轮 Top-5 的 chunk 元数据、matched evidence IDs、Hit@1/5、
first relevant rank、事实覆盖率、完整证据覆盖、耗时和失败原因；汇总 JSON
保留分母、命中率、覆盖率和延迟描述。输出只能写入 `runs/` 且不覆盖已有文件。

真实运行前必须检查 `index.faiss`、`chunks.json` 与语料版本；索引缺失时只记录
阻塞，不填写虚构成绩。结构校验和离线测试不能替代角色④⑥复核、真实模型运行
或下游接收。正式题冻结后再加 `--require-frozen`。

2026-11-03使用N5取件分支的881-chunk同版索引和固定E5/rerank revision做了draft
候选消融：E5-only为8/20，rerank@20为13/20，rerank@50为17/20，
rerank@100为18/20。17/20达到内部门槛数值，但题集尚未双评冻结，候选深度50
也是在当前draft CORE上选择的，因此只能记为候选实验，不能登记N6正式通过。
剩余3道失败为`CORE-FEE-002`、`CORE-REG-002`、`CORE-RES-001`；前三名之后的
原始逐题结果、延迟和失败明细保存在本机`runs/retrieval/`。

## ⑤输出及公平比较约定

结果至少包含实际`case_id/mode/status/answer`、分轮query与Hit、最终上下文chunk IDs、实际引用、tool calls、总耗时与usage、Git/语料/索引/生成模型/prompt版本。待⑤实现，当前不是已取得的运行记录。

分别保留首轮前5条、各轮累计证据、最终上下文与实际引用；不能把多轮累计命中叫Hit@5，也不能只对URL。失败题保留分母。纯LLM没有检索上下文时忠实度N/A；若统一产品成功率要求引用，须声明该要求，与内容正确性分开。

固定问题、生成模型、语言、解码参数、语料与规则视图，并公开总调用预算。usage不可用写null，不估造费用；普通题、澄清、无答案、冲突与故障分层。CORE20的Hit@5≥70%是小组内部门槛，不是课程官方硬指标。小样本报告n/N及限制，重复运行不等于新增独立题。

只有组长明确授权的159条JSONL、脱敏数据库及版本清单进入Git；其他本机数据、`evals/private/`题集、个人结果和`runs/`原始trace保持忽略。不得将密钥、账号、聊天、原始HTTP错误或个人状态写进公开结果。当前N4/N6/N7仍待对应证据与下游接收，结构校验不把它们改成通过。

## ⑥第一版候选

2026-11-01本机候选见[燕萍启动入口](yanping_startup.md)：真实DEV草稿、评分工作台和后端接口核对。私有金标与runs不提交；未运行、未冻结、未代④⑥人工审核。

## 公开结果摘要

2026-11-03的CORE20 draft候选汇总已写入[公开结果目录](results/README.md)。
仓库只保存脱敏指标、版本绑定、消融及失败题ID；私有题集、完整逐题trace和原始
运行报告仍留在本机忽略目录。

## 公开题目清单

2026-11-03的CORE20题干与公开检索状态见
[`evals/results/core20_questions_20261103.md`](results/core20_questions_20261103.md)。
该文件不包含必要事实、标准答案或gold evidence。题目公开后，后续泛化评测必须另用独立未见题。
