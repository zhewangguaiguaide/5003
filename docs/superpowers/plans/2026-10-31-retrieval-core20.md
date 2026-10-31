# CORE20 Retrieval Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first reproducible CORE20 retrieval-evaluation bundle and private annotated case set.

**Architecture:** Case validation reuses `scripts.check_eval_assets`. A pure evaluation module matches normalized gold quotes to top-five chunks, computes metrics, and writes append-only artifacts. The CLI adapts the existing `Retriever` without requiring it in unit tests.

**Tech Stack:** Python 3.12 standard library, `unittest`, existing `src.retriever.Retriever`, JSONL.

**Spec:** `docs/superpowers/specs/2026-10-31-retrieval-core20-design.md`

## Global Constraints

- Bind all cases to corpus SHA256 `2c3f9a2d9dc116062791e8c646ad7e343fd8e22f5a59c91581f84808b0620752`.
- Keep `evals/private/` and `runs/` out of Git.
- Never claim semantic acceptance from structural checks.
- Never fabricate retrieval results when the index/model is unavailable.
- Match evidence by continuous normalized quote, not URL alone.
- Keep failed cases in the denominator.

---

### Task 1: Evaluation primitives and tests

**Files:**
- Create: `scripts/evaluate_wsb.py`
- Create: `tests/test_evaluate_wsb.py`

**Interfaces:**
- Consumes: validated case dictionaries with `required_facts`, `gold_evidence`, and `sufficient_evidence_sets`.
- Produces: `normalize_text(text: str) -> str`, `match_case(case: dict, hits: list, k: int) -> dict`, `summarize_results(rows: list[dict], corpus_sha256: str) -> dict`.

- [ ] Write failing tests for exact quote matching, URL-only non-match, partial facts, complete evidence, failed denominators, output path safety, and CLI rejection of non-retrieval cases.
- [ ] Run `python -m unittest tests.test_evaluate_wsb -v` and verify failure because the module is absent.
- [ ] Implement minimal normalization, matching, metric aggregation, output writers, and CLI.
- [ ] Run `python -m unittest tests.test_evaluate_wsb -v` and verify all tests pass.
- [ ] Run `python -m unittest discover -s tests`.

### Task 2: DEV calibration cases

**Files:**
- Create: `evals/private/dev.jsonl` (ignored)

**Interfaces:**
- Consumes: the existing case contract and corpus.
- Produces: five draft, real, answerable DEV cases with exact evidence.

- [ ] Select three or more topics from the corpus.
- [ ] Add five cases with persona, required facts, gold evidence, and sufficient evidence sets.
- [ ] Run `python -m scripts.check_eval_assets --corpus data/corpus.jsonl --cases evals/private/dev.jsonl`.
- [ ] Fix structural or quote errors until the validator passes.

### Task 3: CORE20 draft cases

**Files:**
- Create: `evals/private/core.jsonl` (ignored)

**Interfaces:**
- Consumes: the same case contract and corpus.
- Produces: twenty draft answerable retrieval cases across all eight topics.

- [ ] Select exact source passages before writing questions.
- [ ] Add twenty cases with unique IDs, evidence, fact links, and sufficient sets.
- [ ] Run `python -m scripts.check_eval_assets --corpus data/corpus.jsonl --cases evals/private/core.jsonl --min-answerable 20`.
- [ ] Review topic coverage and duplicate-intent risk.
- [ ] Fix annotations until the validator passes.

### Task 4: Real-run readiness and artifacts

**Files:**
- Modify: `evals/README.md` only if command usage needs clarification.
- Create locally: `runs/retrieval/...` only when the index is present.

**Interfaces:**
- Consumes: matching corpus, index metadata, and case file.
- Produces: per-case JSONL and aggregate JSON, or an explicit blocked report.

- [ ] Check `data/wsb_index/index.faiss`, `chunks.json`, model availability, and index/corpus consistency.
- [ ] If ready, run the CLI with `--require-frozen`; otherwise record the missing prerequisite without a score.
- [ ] Inspect failed cases and top-five evidence matches.
- [ ] Report retrieval-only metrics and limitations.

### Task 5: Final verification and handoff

**Files:**
- Modify: `docs/协作与需求节点.md` only with verified status and evidence.

**Interfaces:**
- Consumes: test results, validator summaries, and optional real-run output.
- Produces: a concise status update for role4/role6/role5.

- [ ] Run all offline tests and both case validators.
- [ ] Run `git diff --check`.
- [ ] Summarize changed files and private artifacts.
- [ ] List role6 and role5 next tasks without marking their work accepted.
