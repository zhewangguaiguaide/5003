# ⑥燕萍 Agent评测第一版

日期：2026-11-01。状态：候选、待④⑥人工复核及⑤接口对齐；没有模型运行成绩。沿用`evals/README.md`和`evals/rubric.json`。Git基线为6d0ff30，语料SHA为`2c3f9a2d9dc116062791e8c646ad7e343fd8e22f5a59c91581f84808b0620752`。

## 已生成材料

| 文件 | 使用人与用途 | 状态 |
|---|---|---|
| `evals/private/dev.jsonl` | ④⑥：5道正向DEV，包含必要事实、连续原文及充分证据集合 | draft；待独立复核 |
| `evals/private/agent_behavior_dev.jsonl` | ④⑥：3道澄清/个人状态题，不计正向检索分母 | draft |
| `evals/private/燕萍_DEV题与评分工作台.md` | ④⑥：可读题目、证据、通过标准、评分方法、失败分类及引用/超时校准设计 | 待双评 |
| `evals/private/scorecards.jsonl` | 8题×2位评分者，共16条记录 | 全部not_run，分数null |
| `runs/yanping_startup/dev_inputs.jsonl` | ⑤：5题无gold输入 | 已通过白名单导出 |
| `runs/yanping_startup/behavior_inputs.jsonl` | ⑤：3题无gold输入 | 已通过白名单导出 |

**GitHub只包含本入口、接口清单及节点候选状态；上表private/和runs文件仅在燕萍本机，其他人clone不会取得。** 私有金标、工作台与评分表由燕萍另经组内渠道交④；无gold开发输入另交⑤，实际收件与加载后再登记接受，当前未发送。

私有金标、工作台、评分表和runs保持Git忽略；不送入索引或被测模型。没有创建空CORE冒充正式集。首批图书馆题较多，只用于快速校准，不能代表八类业务正式覆盖。本轮仅验证快照内容，没有重新核定官网现行政策。

## 给⑤张宏扬的接口核对清单

以下是待确认要求，不代表接口已存在；没有自动发送消息。

| 核对项 | 最小要求 | 接收状态 |
|---|---|---|
| 调用入口 | Python函数/CLI/API、依赖与最小调用例子 | 待⑤提供 |
| 输入 | case_id及input.query/persona/as_of；不支持的字段明确说明 | 待确认 |
| 模式 | 区分llm/rag/agentic_rag；Web单列，不将--ask算本地RAG | 待确认 |
| 状态 | 成功、澄清、证据不足、工具故障、预算耗尽可诊断 | 待确认 |
| 回答 | 原始answer和真实语言，不只给界面截图 | 待提供 |
| 实际引用 | cited URLs/片段及事实对应；工具取回URL另外记录 | 待提供 |
| 检索轨迹 | 首轮有序Top-5、各轮query/Hit、最终上下文chunk IDs、doc URL及text | 待提供 |
| 工具轨迹 | 工具名、参数、成功/错误、耗时、重试与停止原因 | 待提供 |
| 预算 | 轮数、工具调用次数、总超时分别记录；包括收尾LLM调用 | 待确认 |
| 版本 | Git、语料SHA、索引、embedding、生成模型、prompt | 待提供 |
| 耗时/用量 | 含重试的端到端耗时和实际usage；不可得记null | 待提供 |
| 故障入口 | 隔离注入持续retrieval timeout，不修改正式库，保留真实trace | 待⑤确认 |

输出字段建议：`case_id/mode/status/answer/citations/retrieval_rounds/context_chunk_ids/tool_calls/latency_ms/usage/versions`。版本和usage缺失写null，不编造。状态名及详细结构由④⑤⑥共同确认。

可转发给⑤：

> 张宏扬，我是燕萍，已准备第一版DEV和回答评分表。请给最小后端调用方式，并确认query/persona/as_of输入、answer/status、实际引用、检索轨迹、工具错误、耗时/usage及版本输出。给模型的文件只有无gold输入，金标和预期动作留我与韩上评测侧。还请确认隔离超时测试的注入方式。缺项可以先明确标null，我先校准可测部分。

## 与④韩上对齐

- 候选ID为YP-DEV-001至008，009/010为评分和故障校准设计；先确认ID不冲突再共用。
- ④主做证据与实验运行，⑥主做事实、动作和引用评分；两人独立读原文，不代填审核标记。
- 先双评5道正向DEV，行为与故障场景单列；正式CORE另选至少20题独立事实，不能只换问法。
- N2同版已核，不代表全部政策适用性已核。正式冻结依赖接受范围及④⑥审核；研究目录额外私有原文须另取。
- 复杂冲突/部分可回答场景先做草稿，不硬套当前校验器三类标签。

## 校验与试评分

在仓库根目录执行：

```bash
python -m scripts.check_eval_assets --corpus data/corpus.jsonl --cases evals/private/dev.jsonl
python -m scripts.check_eval_assets --corpus data/corpus.jsonl --cases evals/private/agent_behavior_dev.jsonl
```

本轮上述两项已通过：159篇语料、5道正向DEV和3道行为DEV的字段、SHA及摘录检查通过。无gold输入也已生成；导出器拒绝覆盖，题目更新时用新runs目录。结构通过不证明人工审核、政策现行正确或Agent性能达标。

评分方法沿用rubric：正确性40%、完整性25%、引用25%、表达与行动10%，各0—4。N/A注明原因，按适用权重归一化；未运行null不当0。关键失败单独判定，不被均分抵消。评分工作台附逐事实标签与失败代码。

## 节点及个人素材

N4为候选已生成，待④⑥复核/⑤接口；N7未运行，N8无成绩，N9未封版。本人反馈时间由燕萍另行确认，不预填承诺。唯一节点状态仍维护在`docs/协作与需求节点.md`。

个人评测章节/PPT先准备：场景与DEV/CORE隔离、rubric和关键失败、真实同版结果图（未运行不填数值）、成功及失败修复案例。只负责自己的评测素材，不追加整套报告、PPT或视频统筹。
