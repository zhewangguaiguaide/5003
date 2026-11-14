# 公开评测结果

本目录只保存可公开、脱敏的评测汇总：版本绑定、聚合指标、消融、失败题ID和限制。
完整题目、gold evidence、逐题 Top-5、模型原始trace和个人环境路径继续保留在
`evals/private/` 与 `runs/`，不进入Git。

- [`core20_retrieval_20261103.md`](core20_retrieval_20261103.md)
- [`core20_retrieval_20261103.json`](core20_retrieval_20261103.json)

结构检查或聚合指标不替代role4/role6双评、题集冻结或下游接收。

## 公开题目清单

- [`core20_questions_20261103.md`](core20_questions_20261103.md)
- [`core20_questions_20261103.jsonl`](core20_questions_20261103.jsonl)

题目清单只包含公开题干、persona、as_of和检索状态；必要事实、标准答案、gold evidence和私有评分材料不公开。

## 公开答案键

- [`core20_answers_20261103.md`](core20_answers_20261103.md)
- [`core20_answers_20261103.jsonl`](core20_answers_20261103.jsonl)

答案键包含标准答案和来源URL，不包含私有`required_facts`、`gold_evidence`或逐条证据quote。CORE20题目与答案均已公开，后续不得再把它当作留出测试集。
