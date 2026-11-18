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

③的检索模块不是完整RAG。当前`--ask`是独立Web Agent；⑤的N5 `LocalRAGBackend.ask()`和`--ask-local`已完成固定一次检索的`rag`模式，11/01增加无密钥`mode="retrieval"`/`--retrieve-only`并完成真实链路试查，随后一次DeepSeek回答及引用补验通过（仅开发样例）。11/18新增N7 `AgenticRAGBackend.ask()`和`--local-mode agentic_rag`工程候选，已有动态补检索/主题选择、澄清与预算停止，接口见[开发指导](../docs/Harness开发指导.md#n7-agentic-backend)。四模式统一批量runner及正式成绩仍待完成。④负责实验与统计，⑥负责回答/引用评分。联网模式单列Web，不能把额外外部知识收益全算给Agent编排。

N7工程验证为合成fixture，不是政策金标或正式成绩。对比N5/N7时注入同版Retriever；本轮N7默认仍为E5-only，没有自动采用韩上rerank@50候选。记录`decisions/stop_reason/budget`以及每次模型调用的实际上下文ID/usage；任何一次usage缺失则总usage=null。N5基线继续保留单轮行为。界面补充澄清后以原问题和真实用户条件重新调用，每次ask独立计预算，评测多轮会话时另计整段交互成本，不把多次ask伪装成一次预算内成功。

11/19另有真实N7 DEV与单列回放控制，详见协作页及本机忽略目录`runs/n7-dev-20261119/`。发现v1会漏答子问题却返回answered，原失败保留；当前v2增加一次候选答案覆盖/支持检查，输出`answer_reviews`，其模型调用、usage及耗时全部计入原预算。该检查仅使用原问题、候选断言和实际上下文，不接收gold、评分或预期动作；它仍由同一模型执行，不能充当④⑥独立评分。比较v1/v2或N5/N7时明确版本和额外检查成本，不能混用输出计算成功率。

本轮19次ask包括预算变体、澄清后续及两个无LLM的真实E5短时限注入，不是19个独立样本；32次真实API请求另加1次旧草稿检查，回放控制不计新增API请求。ORCID定义/用途覆盖、借阅具体额度和期限缺口仍保留；没有把安全拒答直接记为任务成功，也没有用多轮累计覆盖冒充首轮Hit@5。正式用例和评分仍由④⑥独立冻结及核验。

11/18只读核对韩上最新分支说明：CORE20题目及答案均已公开，可用于回归，但不再作为未见留出集。本轮不导入答案键或gold到提示词/索引；正式N7效果需DEV先校准、新未见题冻结、N6同版达标及④⑥独立核对。燕萍11/16对原CORE20题目和答案键的本人复核不等于逐题chunk核验、YP-CORE评分或④⑥校准已完成。

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

## 校验与无gold输入导出

先自行完成真实DEV，以下文件必须实际存在：

```powershell
python -m scripts.check_eval_assets --corpus data/corpus.jsonl --cases evals/private/dev.jsonl
python -m scripts.check_eval_assets --corpus data/corpus.jsonl --cases evals/private/dev.jsonl --export-inputs runs/startup/dev_inputs.jsonl
python -m scripts.check_eval_assets --corpus data/corpus.jsonl --cases evals/private/core.jsonl --require-frozen --min-answerable 20
```

工具检查结构、语料SHA、原文摘录、事实/证据引用、充分集合、rubric权重及审核标记，不证明语义正确或审核已实际发生。SHA按文件原始字节计算；换行或重新格式化后需重算并复核，不能填造SHA。

导出只含`case_id`及`input.query/persona/as_of`；ID是评测元数据，不必进入提示词。输出限制在本仓库`runs/`并拒绝覆盖。字段白名单不能替代对persona的人工检查。

## ⑤输出及公平比较约定

结果至少包含实际`case_id/mode/status/answer`、分轮query与Hit、最终上下文chunk IDs、实际引用、tool calls、总耗时与usage、Git/语料/索引/生成模型/prompt版本。N5已提供上述结构，字段与调用见[本地后端接口](../docs/Harness开发指导.md#n5-local-backend)；11/01真实试查绑定语料SHA、E5 revision及索引SHA，5次均有返回不能计为Hit@5=100%，尚无冻结金标。未知版本仍为null，N5旧message-only路径的usage仍为null；N7逐次读取实际元数据（含v2最终检查），缺失时总usage为null。无效引用或生成错误保留为失败结果，不从评测分母剔除。

分别保留首轮前5条、各轮累计证据、最终上下文与实际引用；不能把多轮累计命中叫Hit@5，也不能只对URL。失败题保留分母。纯LLM没有检索上下文时忠实度N/A；若统一产品成功率要求引用，须声明该要求，与内容正确性分开。

固定问题、生成模型、语言、解码参数、语料与规则视图，并公开总调用预算。usage不可用写null，不估造费用；普通题、澄清、无答案、冲突与故障分层。CORE20的Hit@5≥70%是小组内部门槛，不是课程官方硬指标。小样本报告n/N及限制，重复运行不等于新增独立题。

只有组长明确授权的159条JSONL、脱敏数据库及版本清单进入Git；其他本机数据、`evals/private/`题集、个人结果和`runs/`原始trace保持忽略。不得将密钥、账号、聊天、原始HTTP错误或个人状态写进公开结果。当前N4/N6/N7仍待对应证据与下游接收，结构校验不把它们改成通过。
