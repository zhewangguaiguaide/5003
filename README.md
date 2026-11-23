# An Agentic RAG Question-Answering System for CityU Student Services

DSC5003 Database Systems — Track 1: Database Application Development (City University of Hong Kong).

This repository contains the full-stack implementation behind the submitted report and demo video: a
web-corpus pipeline, a SQLite document store, a 881-chunk FAISS evidence index, an evidence-bound
question-answering backend (one-pass N5 path and bounded agentic N7 path), and the F1–F5 evidence
frontend.

## What is in this repository

| Path | Contents |
| --- | --- |
| `src/` | Fetcher, parser, crawler, corpus import, SQLite storage, retriever, answer agent and web-search agent |
| `scripts/` | Index build (`build_wsb_index.py`), corpus/runtime preparation, evaluation and validation helpers |
| `tests/` | Unit and wiring tests (mock site, storage, import, retrieval hooks) |
| `schema.sql` | Physical schema: `documents`, `chunks`, `records`, `corpus_imports`, `crawl_runs`, `qa_logs` |
| `config.yaml` | Topic whitelist, seeds and crawl limits |
| `data/` | Published SQLite database, 159-document corpus, runtime indexed database and the 881-chunk FAISS index |
| `04_前端原型/` | F1–F5 evidence UI and the local answer service used in the demo (Python standard library only) |
| `evals/` | Rubric and evaluation assets |
| `docs/` | Design notes and handover records |
| `knowledge/` | Topic and policy reference notes used during development |

## Quick start — offline demo (no API key)

Requires Python 3.10+ with `sqlite3`. The offline path uses only the standard library.

Windows:

```powershell
git clone https://github.com/zhewangguaiguaide/5003.git
cd 5003
py -3 04_前端原型\app.py --backend . --open
```

macOS / Linux:

```sh
git clone https://github.com/zhewangguaiguaide/5003.git
cd 5003
python3 04_前端原型/app.py --backend . --open
```

The server binds `127.0.0.1` on the first free port in 8501–8510 and prints the URL. Keep the window
open; closing it stops the site. `--backend .` points the frontend at the repository root, where
`data/wsb_index/chunks.json` (881 chunks) and `data/cityu_faq.db` live.

The offline path retrieves from the frozen evidence index and returns extractive answers with S1–S5
citations. It abstains when the retrieved text does not contain the asked attribute, and rejects
out-of-scope questions instead of answering from general knowledge.

## Online answers (optional)

Set a DeepSeek key in the environment, then start the same command:

```powershell
$env:DEEPSEEK_API_KEY = "..."      # PowerShell
python 04_前端原型\app.py --backend . --open
```

```sh
export DEEPSEEK_API_KEY="..."      # macOS / Linux
python3 04_前端原型/app.py --backend . --open
```

The online path retrieves first, generates only from the retrieved evidence, then runs an independent
support review before publishing. If the call fails, the request falls back to offline extraction over
the same 881-chunk evidence base. Keys are never stored in the repository.

## Backend CLI

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m src.main --dry-run
.\.venv\Scripts\python.exe -m src.main --live --mode fake
.\.venv\Scripts\python.exe -m src.main --ask-local "How do I pay my tuition?" --local-mode agentic_rag
```

`--mode fake` uses the synthetic mock site in `tests/mock_site.py`; it uses no network, no API key and
no real corpus, writes `data/demo_fake.db`, and only proves that collection and storage are wired
correctly. `--rag-demo` is likewise a synthetic wiring fixture and must never be read as a CityU policy
answer or counted in evaluation results.

Rebuilding the vector index requires the E5 model and retrieval dependencies:

```powershell
.\.venv\Scripts\python.exe -m scripts.build_wsb_index
```

Model weights are not committed. The committed index is the frozen 881-chunk snapshot used by the demo.

## Data and index versions

- Corpus: 159 documents across 8 topic areas, SHA-256 `2c3f9a2d9dc116062791e8c646ad7e343fd8e22f5a59c91581f84808b0620752`
- Published database (`data/cityu_faq.db`): 159 documents, 83 legacy `records`, 2 `corpus_imports`; `chunks`, `crawl_runs` and `qa_logs` are empty in this published snapshot
- Retrieval index: 881 chunks, 384-dimensional `intfloat/multilingual-e5-small` vectors, FAISS `IndexFlatIP`
- Backend baseline: `c7b067f`; later commits add the N5/N7 answer path, evaluation evidence and the submission frontend
- `data/release_manifest.json` records the published file hashes and validation results

Dataset counts differ by artefact on purpose: the published database stores accepted documents, while
chunks and vectors live in the runtime index and `data/wsb_index/`. Do not merge 0 / 881 / 863 into one
number; they describe different snapshots.

## Evaluation summary

Full results, ablations and error analysis are in the submitted report (Section 5) and reproducible
artefacts under `evals/`.

- R04 CORE20: evidence Hit@5 = 17/20 (85%); rerank depth 50 selected for latency/quality trade-off
- R06 YP-CORE20: strict quoted-span Hit@5 = 15/20 on a *different* 20-case set — not a before/after comparison
- Correct abstentions are reported separately and are not counted as correct answers

## Deliverables

- Report: `An_Agentic_RAG_Question-Answering_System_for_CityU_Student_Services-report.pdf` (submitted separately)
- Video demonstration (6:55): https://drive.google.com/file/d/1Z_EtR71zUYDBEVMvpiBDRjplQVEvmBPM/view?usp=sharing

## Scope and boundaries

- The corpus covers eight CityU student-service topics (159 pages), not the whole university website,
  and it is not a general-purpose assistant.
- A successful SQL query does not establish policy correctness; a retrieved quotation does not prove
  semantic support. The independent review step is a second check, not formal human acceptance.
- The published database snapshot is a development baseline; policy currency is not certified.
- Private evaluation answer keys, model weights, API keys and member handover files are intentionally
  excluded from this repository.