"""Build a provenance-bound development index and a separate runtime database.

Reuses role 3's chunk_records unchanged. Published data is read-only; this is a
candidate integration build, not policy review or retrieval-performance acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.retriever import chunk_records, load_corpus

MODEL = "intfloat/multilingual-e5-small"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_snapshot(corpus, database):
    """Check all delivered fields against the active DB, without reading logs."""
    records = load_corpus(corpus)
    digest = sha256(corpus)
    if not records or len({r["url"] for r in records}) != len(records):
        raise ValueError("Corpus must contain unique nonempty documents")
    conn = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Database foreign-key check failed")
        rows = {r["url"]: dict(r) for r in conn.execute("SELECT * FROM documents WHERE active=1")}
        if set(rows) != {r["url"] for r in records}:
            raise ValueError("Database and corpus contain different active documents")
        for record in records:
            row = rows[record["url"]]
            if row["corpus_sha256"] != digest:
                raise ValueError("Database corpus SHA does not match JSONL bytes")
            for key, value in record.items():
                if key == "error":
                    if value:
                        raise ValueError("Corpus contains failed document")
                    continue
                actual = row["column_name" if key == "column" else key]
                if key in ("image_urls", "file_urls"):
                    actual = json.loads(actual)
                if actual != value:
                    raise ValueError(f"Database/corpus field mismatch: {key}")
    finally:
        conn.close()
    return records, digest


def build(corpus, database, index_dir, runtime_db, model_path, revision):
    import faiss
    import numpy as np
    from src.embedding_worker import LocalEncoder
    faiss.omp_set_num_threads(1)

    corpus, database = Path(corpus), Path(database)
    index_dir, runtime_db, model_path = Path(index_dir), Path(runtime_db), Path(model_path)
    if index_dir.exists() or runtime_db.exists():
        raise ValueError("Use new index/runtime paths; existing artifacts are never overwritten")
    if database.resolve() == runtime_db.resolve():
        raise ValueError("Runtime database must differ from the published input")
    if not revision or len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("Provide the exact model commit SHA")
    if (model_path / "REVISION").read_text().strip() != revision:
        raise ValueError("Model folder revision does not match requested build")
    original_db_sha = sha256(database)
    records, corpus_sha = verify_snapshot(corpus, database)
    chunks = chunk_records(records)
    if not chunks or len({c.chunk_id for c in chunks}) != len(chunks):
        raise ValueError("Chunk IDs must be nonempty and unique")
    print(f"Verified {len(records)} documents; building {len(chunks)} chunks.", flush=True)
    model = LocalEncoder(str(model_path.resolve()))
    texts = ["passage: " + c.text for c in chunks]
    lengths = model.token_counts(texts)
    truncated = [c.chunk_id for c, length in zip(chunks, lengths) if length > model.max_seq_length]
    print(f"Tokenizer limit {model.max_seq_length}; over-limit chunks: {len(truncated)}.", flush=True)
    vectors = np.asarray(model.encode(texts, batch_size=16, normalize_embeddings=True,
                                     show_progress_bar=True, convert_to_numpy=True), dtype=np.float32)
    max_seq_length = model.max_seq_length
    model.close()
    if not np.isfinite(vectors).all() or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5):
        raise ValueError("Embedding vectors are not finite normalized values")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    indexed_ids = {c.doc_id for c in chunks}
    index_dir.parent.mkdir(parents=True, exist_ok=True)
    runtime_db.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".n5-build-", dir=index_dir.parent))
    runtime_temp = runtime_db.with_name(runtime_db.name + ".building")
    if runtime_temp.exists():
        shutil.rmtree(staging)
        raise ValueError("A previous runtime staging file exists; inspect it before retrying")
    try:
        (staging / "index.faiss").write_bytes(faiss.serialize_index(index).tobytes())
        model_hashes = {p.relative_to(model_path).as_posix(): sha256(p)
                        for p in sorted(model_path.rglob("*"))
                        if p.is_file() and ".cache" not in p.relative_to(model_path).parts}
        metadata = {
            "model": MODEL, "dimension": int(vectors.shape[1]),
            "model_revision": revision, "model_files_sha256": model_hashes,
            "corpus_sha256": corpus_sha, "source_database_sha256": original_db_sha,
            "index_sha256": sha256(staging / "index.faiss"),
            "provenance_version": 1, "query_prefix": "query: ", "passage_prefix": "passage: ",
            "normalize_embeddings": True, "database_chunk_binding": True,
            "device": "cpu", "cpu_threads": 1, "encoder_process": "isolated",
            "chunking_source_sha256": sha256(Path(__file__).parents[1] / "src/retriever.py"),
            "build_tool_sha256": sha256(Path(__file__)),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "max_seq_length": int(max_seq_length), "over_limit_chunk_ids": truncated,
            "unindexed_document_ids": sorted({r["url"] for r in records} - indexed_ids),
            "chunks": [asdict(c) for c in chunks],
        }
        (staging / "chunks.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        source = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        target = sqlite3.connect(runtime_temp)
        try:
            source.backup(target)
            target.execute("PRAGMA foreign_keys=ON")
            with target:
                target.execute("DELETE FROM chunks")
                target.executemany("INSERT INTO chunks(chunk_id,doc_id,ord,text) VALUES (?,?,?,?)",
                                   [(c.chunk_id, c.doc_id, int(c.chunk_id.rsplit('-', 1)[1]), c.text) for c in chunks])
                target.executemany("UPDATE documents SET index_dirty=0 WHERE url=? AND corpus_sha256=? AND active=1",
                                   [(url, corpus_sha) for url in sorted(indexed_ids)])
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Runtime database integrity failed")
            if target.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Runtime database has invalid chunk references")
        finally:
            source.close()
            target.close()
        if sha256(database) != original_db_sha or sha256(corpus) != corpus_sha:
            raise ValueError("Source data changed during build; refuse publication")
        staging.rename(index_dir)
        runtime_temp.rename(runtime_db)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"status": "built_candidate", "documents": len(records), "chunks": len(chunks),
            "indexed_documents": len(indexed_ids), "over_limit_chunks": len(truncated),
            "dimension": int(vectors.shape[1]), "corpus_sha256": corpus_sha,
            "model_revision": revision, "index_dir": str(index_dir), "runtime_db": str(runtime_db)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="data/corpus.jsonl")
    parser.add_argument("--database", default="data/cityu_faq.db")
    parser.add_argument("--index-dir", default="data/wsb_index")
    parser.add_argument("--runtime-db", default="data/runtime_indexed.db")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--model-revision", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.corpus, args.database, args.index_dir, args.runtime_db,
                           args.model_path, args.model_revision), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
