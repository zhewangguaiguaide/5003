# CORE20 Retrieval Evaluation Summary

Date: 2026-11-03  
Status: **draft candidate, not frozen**  
Scope: retrieval evidence only; no LLM/RAG/agentic answer-quality claim.

## Run configuration

| Item | Value |
|---|---|
| Corpus SHA256 | `2c3f9a2d9dc116062791e8c646ad7e343fd8e22f5a59c91581f84808b0620752` |
| Index chunks | 881 |
| Index SHA256 | `2e6b7edcac34c1b07ce5f81860ff61d85129b64fe3d07101435d54eec1129590` |
| Embedding model / revision | `intfloat/multilingual-e5-small` / `614241f622f53c4eeff9890bdc4f31cfecc418b3` |
| Rerank model / revision | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` / `1427fd652930e4ba29e8149678df786c240d8825` |
| Retrieval k | 5 |
| Rerank candidate depth | 50 |
| Cases | 20 |

## Results

| Metric | Result |
|---|---:|
| Hit@1 | 9/20 (45%) |
| Hit@5 | 17/20 (85%) |
| Mean fact coverage | 85.00% |
| Mean critical fact coverage | 85.00% |
| Complete evidence coverage | 17/20 (85%) |
| Latency mean / median / p95 / max | 2.775s / 2.699s / 3.377s / 5.871s |

## Ablation

| Configuration | Hit@5 |
|---|---:|
| E5 only | 8/20 (40%) |
| E5 + rerank@20 | 13/20 (65%) |
| E5 + rerank@50 | 17/20 (85%) |
| E5 + rerank@100 | 18/20 (90%) |

The internal gate is Hit@5 ≥ 70%. The draft candidate records 17/20, but it is not an
official N6 acceptance result: the cases are not frozen, role4/role6 review is pending,
and candidate depth 50 was selected on the current draft CORE set.

## Remaining failures

- `CORE-FEE-002`: late-payment charge evidence chunk not in Top-5
- `CORE-REG-002`: late-drop/X-grade evidence chunk not in Top-5
- `CORE-RES-001`: 2026/27 hall application-period evidence chunk not in Top-5

These are chunk-ranking failures, not missing source quotations. No answer-quality
conclusion is drawn.

## Reproducibility and privacy

The runner is `scripts/evaluate_wsb.py`. It supports pinned local embedding/rerank
models and configurable candidate depth. The complete private case annotations,
per-question traces and run report remain in `evals/private/` and `runs/` and are
not committed. Machine-readable public metrics are in
`evals/results/core20_retrieval_20261103.json`.

## Limitations

- English retrieval path only.
- Two published corpus pages have no indexed chunks; none of the CORE20 evidence depends on them.
- Hit@5 uses exact continuous-quote evidence matching, not URL-only matching.
- Model binaries, private gold and raw traces are not in Git.
