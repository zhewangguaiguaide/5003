"""Offline structural checks and gold-free input export; no model scoring."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_FIELDS = {
    "url", "title", "source", "content", "date", "crawled_at", "academic_year",
    "topic", "column", "error", "image_urls", "file_urls",
}
CASE_FIELDS = {
    "id", "split", "synthetic", "review_status", "query", "persona", "as_of",
    "answerability", "expected_action", "required_facts", "gold_evidence",
    "sufficient_evidence_sets", "forbidden_claims", "required_clarifications",
    "retrieval_applicable", "corpus_sha256", "gold_version", "human_reviewed",
    "reviewer_roles",
}


class AssetError(ValueError):
    """Invalid input, reported without dumping source content."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssetError(message)


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            raise AssetError(f"{path.name}: line {line_no}: invalid JSON") from None
        require(isinstance(row, dict), f"{path.name}: line {line_no}: expected object")
        rows.append(row)
    require(bool(rows), f"{path.name}: empty JSONL")
    return rows


def unique_objects(rows: object, label: str) -> dict[str, dict]:
    require(isinstance(rows, list), f"{label}: expected list")
    result = {}
    for row in rows:
        require(isinstance(row, dict) and nonempty(row.get("id")), f"{label}: missing id")
        require(row["id"] not in result, f"{label}: duplicate id")
        result[row["id"]] = row
    return result


def string_list(value: object, label: str) -> None:
    require(isinstance(value, list) and all(nonempty(v) for v in value),
            f"{label}: expected list of nonempty strings")


def validate_bundle(corpus_path: Path, cases_path: Path, rubric_path: Path,
                    *, require_frozen: bool = False, min_answerable: int = 0) -> dict:
    corpus = read_jsonl(corpus_path)
    cases = read_jsonl(cases_path)
    digest = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    documents = {}
    for n, doc in enumerate(corpus, 1):
        label = f"corpus row {n}"
        require(CORPUS_FIELDS <= doc.keys(), f"{label}: missing corpus fields")
        for key in CORPUS_FIELDS - {"image_urls", "file_urls"}:
            require(isinstance(doc[key], str), f"{label}: {key} must be string")
        for key in ("image_urls", "file_urls"):
            string_list(doc[key], f"{label}: {key}")
        require(nonempty(doc["url"]) and nonempty(doc["content"]), f"{label}: empty URL/content")
        require(not doc["error"], f"{label}: error record cannot be a gold source")
        require(doc["url"] not in documents, f"{label}: duplicate URL")
        documents[doc["url"]] = doc

    unique_objects(cases, "cases")
    answerable_count = 0
    for n, case in enumerate(cases, 1):
        label = f"case row {n}"
        require(CASE_FIELDS <= case.keys(), f"{label}: missing case fields")
        require(case["corpus_sha256"] == digest, f"{label}: corpus SHA256 mismatch")
        require(nonempty(case["query"]) and nonempty(case["gold_version"]),
                f"{label}: query/gold_version required")
        require(isinstance(case["persona"], dict) and
                all(isinstance(k, str) and isinstance(v, str) for k, v in case["persona"].items()),
                f"{label}: persona must contain only user-known string conditions")
        try:
            date.fromisoformat(case["as_of"])
        except (TypeError, ValueError):
            raise AssetError(f"{label}: invalid as_of date") from None
        require(case["split"] in ("dev", "test"), f"{label}: unknown split")
        require(case["review_status"] in ("draft", "synthetic_ready", "frozen"),
                f"{label}: unknown review_status")
        for key in ("synthetic", "human_reviewed", "retrieval_applicable"):
            require(type(case[key]) is bool, f"{label}: {key} must be boolean")
        for key in ("forbidden_claims", "required_clarifications", "reviewer_roles"):
            string_list(case[key], f"{label}: {key}")
        if require_frozen or case["review_status"] == "frozen":
            require(case["synthetic"] is False and case["split"] == "test" and
                    case["review_status"] == "frozen" and case["human_reviewed"] is True and
                    {"role4", "role6"} <= set(case["reviewer_roles"]),
                    f"{label}: frozen requires real TEST and role4/role6 review markers")
        if case["review_status"] == "synthetic_ready":
            require(case["synthetic"] and case["split"] == "dev",
                    f"{label}: synthetic_ready requires synthetic DEV")

        facts = unique_objects(case["required_facts"], f"{label}: facts")
        evidence = unique_objects(case["gold_evidence"], f"{label}: evidence")
        for fact in facts.values():
            require(nonempty(fact.get("text")) and type(fact.get("critical")) is bool,
                    f"{label}: fact needs text and critical boolean")
        for item in evidence.values():
            require(isinstance(item.get("doc_id"), str) and item["doc_id"] in documents,
                    f"{label}: evidence source absent from corpus")
            require(nonempty(item.get("locator")) and nonempty(item.get("quote")),
                    f"{label}: evidence needs locator and quote")
            require(item["quote"] in documents[item["doc_id"]]["content"],
                    f"{label}: quote absent from source content")
            string_list(item.get("fact_ids"), f"{label}: fact_ids")
            require(bool(item["fact_ids"]) and set(item["fact_ids"]) <= facts.keys(),
                    f"{label}: unknown or empty fact reference")
        sets = case["sufficient_evidence_sets"]
        require(isinstance(sets, list), f"{label}: sufficient_evidence_sets must be list")
        for group in sets:
            string_list(group, f"{label}: evidence set")
            require(bool(group) and set(group) <= evidence.keys(),
                    f"{label}: unknown or empty evidence reference")
            covered = {f for item_id in group for f in evidence[item_id]["fact_ids"]}
            require(covered == facts.keys(), f"{label}: evidence set misses required facts")

        kind, action = case["answerability"], case["expected_action"]
        if kind == "answerable":
            require(action == "answer" and bool(facts) and bool(evidence) and bool(sets)
                    and case["retrieval_applicable"] and not case["required_clarifications"],
                    f"{label}: answerable needs facts, evidence, sets and answer action")
            answerable_count += 1
        elif kind == "clarify":
            require(action == "clarify" and bool(case["required_clarifications"]),
                    f"{label}: clarify needs clarification fields")
        elif kind == "unanswerable":
            require(action in ("abstain", "refer") and not case["required_clarifications"],
                    f"{label}: unanswerable needs abstain/refer action")
        else:
            raise AssetError(f"{label}: unsupported answerability")
        if kind != "answerable":
            require(not case["retrieval_applicable"] and not facts and not evidence and not sets,
                    f"{label}: non-answerable cases excluded from positive retrieval denominator")

    try:
        rubric = json.loads(rubric_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        raise AssetError("rubric: invalid JSON") from None
    require(isinstance(rubric, dict) and nonempty(rubric.get("version")), "rubric: missing version")
    dimensions = unique_objects(rubric.get("dimensions"), "rubric dimensions")
    require(bool(dimensions), "rubric: empty dimensions")
    for dimension in dimensions.values():
        weight = dimension.get("weight")
        anchors = dimension.get("anchors")
        require(type(weight) in (int, float) and 0 < weight <= 100, "rubric: invalid weight")
        require(isinstance(anchors, dict) and set(anchors) == {str(i) for i in range(5)} and
                all(nonempty(v) for v in anchors.values()), "rubric: anchors must cover 0-4")
    require(sum(d["weight"] for d in dimensions.values()) == 100, "rubric: weights must sum to 100")
    require(min_answerable >= 0 and answerable_count >= min_answerable,
            "not enough retrieval-applicable answerable cases")
    return {"documents": len(corpus), "cases": len(cases), "answerable": answerable_count,
            "corpus_sha256": digest, "rubric_version": rubric["version"]}


def export_inputs(cases_path: Path, destination: Path, *, root: Path = ROOT) -> None:
    """Copy an explicit whitelist; gold and labels never enter exported inputs."""
    allowed = (root / "runs").resolve()
    target = destination.resolve()
    require(target != allowed and target.is_relative_to(allowed), "export must be inside repository runs/")
    require(not target.exists(), "export refuses to overwrite existing file")
    inputs = [{"case_id": case["id"], "input": {
        "query": case["query"], "persona": case["persona"], "as_of": case["as_of"],
    }} for case in read_jsonl(cases_path)]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        for item in inputs:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "evals/synthetic_corpus.jsonl")
    parser.add_argument("--cases", type=Path, default=ROOT / "evals/dev_cases.jsonl")
    parser.add_argument("--rubric", type=Path, default=ROOT / "evals/rubric.json")
    parser.add_argument("--require-frozen", action="store_true")
    parser.add_argument("--min-answerable", type=int, default=0)
    parser.add_argument("--export-inputs", type=Path)
    args = parser.parse_args(argv)
    try:
        summary = validate_bundle(args.corpus, args.cases, args.rubric,
                                  require_frozen=args.require_frozen,
                                  min_answerable=args.min_answerable)
        if args.export_inputs:
            export_inputs(args.cases, args.export_inputs)
    except (AssetError, OSError, UnicodeError) as error:
        # Do not expose paths, source text, HTTP responses or credentials from OS errors.
        message = str(error) if isinstance(error, AssetError) else type(error).__name__
        print(f"FAIL: {message}")
        return 1
    print(json.dumps(summary, ensure_ascii=False))
    print("PASS: structural checks only; no semantic review or model performance acceptance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
