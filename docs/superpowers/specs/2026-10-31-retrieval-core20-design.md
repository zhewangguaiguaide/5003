# CORE20 Retrieval Evaluation Design

**Date:** 2026-10-31  
**Status:** approved for first implementation  
**Owner:** role4  
**Reviewer:** role6

## Goal

Create the first reproducible retrieval-evaluation bundle for the published
159-document CityUHK corpus: five DEV calibration cases, twenty CORE retrieval
cases with evidence annotations, a retrieval runner that reports per-question
results, and offline tests. LLM, RAG, and agentic answer scoring are reserved
for a later increment.

## Inputs and version binding

- Corpus: `data/corpus.jsonl`
- Corpus SHA256: `2c3f9a2d9dc116062791e8c646ad7e343fd8e22f5a59c91581f84808b0620752`
- Case annotations: `evals/private/dev.jsonl` and `evals/private/core.jsonl`
  (ignored by Git)
- Retrieval index: `data/wsb_index/` supplied by the retrieval owner
- Published baseline: `data/release_manifest.json`

The first case set is draft and bound to the corpus bytes. A later knowledge
base upload may add rule mappings but does not change the source snapshot or
retroactively freeze the cases. Cases may be frozen only after role4 and role6
cross-review and the existing `check_eval_assets.py --require-frozen` contract
passes.

## Deliverables

1. Five real DEV cases for calibration, covering at least three topics and the
   annotation workflow.
2. Twenty answerable, retrieval-applicable CORE cases covering the eight
   published topics. Every case contains required facts, exact continuous
   source quotes, evidence-to-fact links, and sufficient evidence sets.
3. `scripts/evaluate_wsb.py`, a CLI and importable module that:
   - loads validated case annotations;
   - calls `Retriever.search(query, topic=None, k=5)`;
   - matches evidence by normalized continuous quote inside returned chunk
     text, not by URL alone;
   - reports Hit@1, Hit@5, first relevant rank, fact coverage, complete evidence
     coverage, latency, top-five metadata, and failure reasons;
   - writes per-case JSONL and aggregate JSON without overwriting prior runs;
   - refuses gold inputs without the current corpus SHA.
4. `tests/test_evaluate_wsb.py`, using a fake retriever so unit tests do not
   require FAISS, model weights, or network access.
5. A local run result only when a real index exists. Missing index or model is
   reported as blocked; performance numbers are never fabricated.

## Evaluation semantics

- Retrieval denominator: answerable cases with `retrieval_applicable=true`.
- Hit@5: at least one top-five hit contains a gold evidence quote whose
  `fact_ids` are relevant to a required fact.
- Fact coverage: number of distinct required fact IDs supported by any top-five
  hit divided by all required fact IDs.
- Critical fact coverage: the same calculation restricted to facts marked
  `critical=true`.
- Complete evidence coverage: any annotated sufficient evidence set is fully
  matched by top-five hits.
- First relevant rank: lowest one-based rank with any exact evidence-quote
  match; null when no match exists.
- Failed cases remain in the denominator.
- Latency is wall-clock seconds per query and is descriptive only for this small
  sample.

## Matching rules

Whitespace is normalized before quote comparison. A gold evidence item matches a
hit only when its quote appears continuously in that hit's text after
normalization. A URL match without quote support is not a hit. Multiple evidence
items may match the same chunk, and equivalent evidence sets are allowed.

## CLI contract

```bash
python -m scripts.evaluate_wsb \
  --cases evals/private/core.jsonl \
  --index-dir data/wsb_index \
  --output runs/retrieval/core20_results.jsonl \
  --summary runs/retrieval/core20_summary.json \
  --k 5
```

Optional `--require-frozen` is passed to the existing asset validator. Output
paths must resolve inside repository `runs/` and must not already exist.
Non-answerable or non-retrieval cases are rejected from this retrieval run.

## Results schema

Per-case JSONL records include:

- `case_id`, `query`, `status`, `k`
- `top_hits`: rank, chunk_id, doc_id, url, title, topic, score, matched evid IDs
- `hit_at_1`, `hit_at_5`, `first_relevant_rank`
- `fact_coverage`, `critical_fact_coverage`, `complete_evidence`
- `covered_fact_ids`, `missing_fact_ids`
- `latency_seconds`, `failure_reasons`

Aggregate JSON includes corpus SHA, case count, metrics, latency summary, and an
explicit statement that this is retrieval-only evidence, not answer quality.

## Division of work

Role4 (this implementation) owns retrieval-positive cases, evidence annotation,
the evaluator, retrieval statistics, and per-question output. Role6 owns
clarification/unanswerable/fault scenarios, expected-action and required-fact
cross-review, rubric calibration, golden answers, and later answer/citation
scoring. Role5 later supplies versioned LLM/RAG/agentic outputs using the same
case IDs. Private gold and raw traces remain under ignored directories.

## Testing

- TDD for quote normalization, URL-only false positives, partial versus complete
  evidence, metric denominators, output path safety, and CLI behavior.
- Run `python -m unittest discover -s tests`.
- Run `python -m scripts.check_eval_assets` on both private case files.
- Run the real evaluator only if a compatible index and model are present.

## Non-goals

- Automated semantic answer correctness.
- LLM-as-judge scoring.
- LLM, RAG, or agentic performance claims.
- Modifying the published corpus, index, or knowledge-base facts.
