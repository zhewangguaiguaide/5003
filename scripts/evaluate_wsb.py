"""Offline retrieval evaluation for annotated WSB cases; no answer scoring."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from scripts.check_eval_assets import AssetError, read_jsonl, validate_bundle

ROOT = Path(__file__).resolve().parents[1]


def normalize_text(text: str) -> str:
    """Normalize only whitespace so a gold quote remains a continuous match."""
    return " ".join(str(text).split())


def _hit_value(item: Any, key: str, default: Any = "") -> Any:
    return getattr(item, key, default)


def match_case(case: dict, hits: Iterable[Any], k: int = 5) -> dict:
    """Match gold evidence quotes against the first k retrieval hits."""
    if k <= 0:
        raise AssetError("k must be positive")

    facts = case["required_facts"]
    evidence = case["gold_evidence"]
    sets = case["sufficient_evidence_sets"]
    fact_order = [fact["id"] for fact in facts]
    critical_order = [fact["id"] for fact in facts if fact.get("critical")]

    top_hits = []
    matched_evidence: set[str] = set()
    first_relevant_rank = None

    for rank, item in enumerate(list(hits)[:k], 1):
        text = normalize_text(_hit_value(item, "text"))
        doc_id = _hit_value(item, "doc_id") or _hit_value(item, "url")
        matched_here = []
        for gold in evidence:
            quote = normalize_text(gold["quote"])
            if gold["doc_id"] == doc_id and quote in text:
                matched_here.append(gold["id"])
                matched_evidence.add(gold["id"])
        if matched_here and first_relevant_rank is None:
            first_relevant_rank = rank
        try:
            score = float(_hit_value(item, "score"))
        except (TypeError, ValueError):
            score = None
        top_hits.append({
            "rank": rank,
            "chunk_id": _hit_value(item, "chunk_id"),
            "doc_id": doc_id,
            "url": _hit_value(item, "url") or doc_id,
            "title": _hit_value(item, "title"),
            "topic": _hit_value(item, "topic"),
            "score": score,
            "matched_evidence_ids": matched_here,
        })

    covered_set = {
        fact_id
        for gold in evidence
        if gold["id"] in matched_evidence
        for fact_id in gold["fact_ids"]
    }
    covered = [fact_id for fact_id in fact_order if fact_id in covered_set]
    missing = [fact_id for fact_id in fact_order if fact_id not in covered_set]
    covered_critical = [fact_id for fact_id in critical_order if fact_id in covered_set]
    complete_evidence = any(
        bool(group) and set(group) <= matched_evidence for group in sets
    )

    failure_reasons = []
    if not top_hits:
        failure_reasons.append("no_hits")
    elif first_relevant_rank is None:
        failure_reasons.append("no_evidence_quote_in_top_k")
    if missing:
        failure_reasons.append("missing_required_facts")
    if not complete_evidence:
        failure_reasons.append("no_complete_evidence_set")

    return {
        "case_id": case["id"],
        "query": case["query"],
        "status": "ok",
        "k": k,
        "hit_at_1": first_relevant_rank == 1,
        "hit_at_5": first_relevant_rank is not None and first_relevant_rank <= 5,
        "first_relevant_rank": first_relevant_rank,
        "fact_coverage": len(covered) / len(fact_order) if fact_order else 0.0,
        "critical_fact_coverage": (
            len(covered_critical) / len(critical_order) if critical_order else 1.0
        ),
        "complete_evidence": complete_evidence,
        "covered_fact_ids": covered,
        "missing_fact_ids": missing,
        "top_hits": top_hits,
        "latency_seconds": None,
        "failure_reasons": failure_reasons,
    }


def summarize_results(rows: list[dict], corpus_sha256: str) -> dict:
    """Aggregate case rows without treating retrieval as answer correctness."""
    if not rows:
        raise AssetError("no cases to summarize")

    case_count = len(rows)
    hit_at_1_count = sum(bool(row.get("hit_at_1")) for row in rows)
    hit_at_5_count = sum(bool(row.get("hit_at_5")) for row in rows)
    complete_count = sum(bool(row.get("complete_evidence")) for row in rows)
    latencies = [
        float(row["latency_seconds"])
        for row in rows
        if row.get("latency_seconds") is not None
    ]
    failure_counts = Counter(
        reason for row in rows for reason in row.get("failure_reasons", [])
    )

    latency_summary = None
    if latencies:
        ordered = sorted(latencies)
        p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
        latency_summary = {
            "count": len(ordered),
            "mean": statistics.fmean(ordered),
            "median": statistics.median(ordered),
            "p95": ordered[p95_index],
            "max": max(ordered),
        }

    return {
        "cases": case_count,
        "corpus_sha256": corpus_sha256,
        "hit_at_1": {
            "count": hit_at_1_count,
            "rate": hit_at_1_count / case_count,
        },
        "hit_at_5": {
            "count": hit_at_5_count,
            "rate": hit_at_5_count / case_count,
        },
        "mean_fact_coverage": statistics.fmean(
            float(row.get("fact_coverage", 0.0)) for row in rows
        ),
        "mean_critical_fact_coverage": statistics.fmean(
            float(row.get("critical_fact_coverage", 0.0)) for row in rows
        ),
        "complete_evidence": {
            "count": complete_count,
            "rate": complete_count / case_count,
        },
        "failure_counts": dict(sorted(failure_counts.items())),
        "latency_seconds": latency_summary,
        "retrieval_only": True,
        "semantic_answer_quality": False,
        "note": "Retrieval evidence metrics only; not LLM, RAG, or agentic answer quality.",
    }


def ensure_retrieval_cases(cases: list[dict]) -> None:
    """Reject cases that are outside the positive-retrieval denominator."""
    if not cases:
        raise AssetError("no cases supplied")
    for case in cases:
        if case.get("answerability") != "answerable" or case.get("retrieval_applicable") is not True:
            raise AssetError(
                f"case {case.get('id', '<unknown>')}: retrieval evaluator requires "
                "answerable retrieval-applicable cases"
            )
        if not case.get("required_facts") or not case.get("gold_evidence"):
            raise AssetError(f"case {case['id']}: retrieval gold is incomplete")
        if not case.get("sufficient_evidence_sets"):
            raise AssetError(f"case {case['id']}: sufficient evidence sets are required")


def run_evaluation(cases: list[dict], retriever: Any, k: int = 5) -> list[dict]:
    """Run retrieval per case and retain errors in the evaluation denominator."""
    ensure_retrieval_cases(cases)
    rows = []
    for case in cases:
        started = time.perf_counter()
        try:
            hits = retriever.search(case["query"], topic=None, k=k)
            row = match_case(case, hits, k=k)
        except Exception as error:  # Keep one broken query from hiding the remaining cases.
            row = {
                "case_id": case["id"],
                "query": case["query"],
                "status": "error",
                "k": k,
                "hit_at_1": False,
                "hit_at_5": False,
                "first_relevant_rank": None,
                "fact_coverage": 0.0,
                "critical_fact_coverage": 0.0,
                "complete_evidence": False,
                "covered_fact_ids": [],
                "missing_fact_ids": [fact["id"] for fact in case["required_facts"]],
                "top_hits": [],
                "failure_reasons": ["retriever_error"],
                "error_type": type(error).__name__,
            }
        row["latency_seconds"] = time.perf_counter() - started
        rows.append(row)
    return rows


def _ensure_output_path(path: Path, *, root: Path) -> Path:
    runs = (root / "runs").resolve()
    target = path.resolve()
    if target == runs or not target.is_relative_to(runs):
        raise AssetError("output must be inside repository runs/")
    if target.exists():
        raise AssetError("output refuses to overwrite existing file")
    return target


def write_results(
    rows: list[dict],
    summary: dict,
    output: Path,
    summary_path: Path,
    *,
    root: Path = ROOT,
) -> None:
    """Write append-only JSONL and JSON artifacts inside runs/."""
    target = _ensure_output_path(output, root=root)
    summary_target = _ensure_output_path(summary_path, root=root)
    if target == summary_target:
        raise AssetError("output and summary paths must differ")

    target.parent.mkdir(parents=True, exist_ok=True)
    summary_target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    with summary_target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def validate_index_corpus_alignment(index_dir: Path, corpus_path: Path) -> int:
    """Check index metadata does not reference documents absent from the corpus."""
    index_file = index_dir / "index.faiss"
    chunks_file = index_dir / "chunks.json"
    if not index_file.is_file() or not chunks_file.is_file():
        raise AssetError("retrieval index files are missing")
    try:
        metadata = json.loads(chunks_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise AssetError("index chunks metadata is invalid JSON") from None
    chunks = metadata.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise AssetError("index chunks metadata is empty")
    corpus = read_jsonl(corpus_path)
    corpus_urls = {row["url"] for row in corpus}
    unknown = sorted({
        chunk.get("doc_id", "")
        for chunk in chunks
        if isinstance(chunk, dict) and chunk.get("doc_id") not in corpus_urls
    })
    if unknown:
        raise AssetError("index references documents absent from the corpus")
    return len(chunks)


def load_private_cases(
    corpus: Path,
    cases: Path,
    rubric: Path,
    *,
    require_frozen: bool,
) -> list[dict]:
    validate_bundle(
        corpus,
        cases,
        rubric,
        require_frozen=require_frozen,
        min_answerable=1,
    )
    loaded = read_jsonl(cases)
    ensure_retrieval_cases(loaded)
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "data/corpus.jsonl")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--rubric", type=Path, default=ROOT / "evals/rubric.json")
    parser.add_argument("--index-dir", type=Path, default=ROOT / "data/wsb_index")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--require-frozen", action="store_true")
    args = parser.parse_args(argv)

    if args.k <= 0:
        print("FAIL: k must be positive")
        return 1
    try:
        _ensure_output_path(args.output, root=ROOT)
        _ensure_output_path(args.summary, root=ROOT)
        cases = load_private_cases(
            args.corpus, args.cases, args.rubric,
            require_frozen=args.require_frozen,
        )
        index_chunks = validate_index_corpus_alignment(args.index_dir, args.corpus)
        from src.retriever import Retriever

        retriever = Retriever(str(args.index_dir))
        rows = run_evaluation(cases, retriever, k=args.k)
        summary = summarize_results(rows, read_manifest_corpus_sha(args.corpus))
        summary["index_chunks"] = index_chunks
        summary["k"] = args.k
        write_results(rows, summary, args.output, args.summary, root=ROOT)
    except (AssetError, OSError, UnicodeError, ImportError, ModuleNotFoundError) as error:
        message = str(error) if isinstance(error, AssetError) else type(error).__name__
        print(f"FAIL: {message}")
        return 1

    print(json.dumps(summary, ensure_ascii=False))
    print("PASS: retrieval run completed; answer quality was not scored.")
    return 0


def read_manifest_corpus_sha(corpus_path: Path) -> str:
    """Return the SHA recorded by the asset validator's exact byte semantics."""
    import hashlib

    return hashlib.sha256(corpus_path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
