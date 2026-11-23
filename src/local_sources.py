"""Read-only N5 adapters for existing N3 artifacts and accepted documents.

Bound development artifacts verify corpus/model/index identity and DB chunks.
Legacy artifacts remain supported with explicit warnings; neither certifies N2.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .retriever import Retriever
from .embedding_worker import LocalEncoder


E5_MODEL = "intfloat/multilingual-e5-small"


class LocalSourceError(RuntimeError):
    """Stable public error code and safe message; raw errors stay in the cause."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_retriever(index_dir: str | Path, model_path: str | Path | None = None) -> tuple[Retriever, dict, list[str]]:
    """Load the existing Retriever and locally cached E5; never fetch a model.

    Metadata model/dimension/count are checked against actual loaded objects.
    Revision and corpus identity remain unknown for legacy unbound artifacts.
    """
    directory = Path(index_dir)
    index_path = directory / "index.faiss"
    chunks_path = directory / "chunks.json"
    try:
        hashes = (_sha256(index_path), _sha256(chunks_path))
        metadata = json.loads(chunks_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LocalSourceError(
            "index_unavailable", "Local index files are missing, unreadable or invalid."
        ) from exc

    if not isinstance(metadata, dict) or metadata.get("model") != E5_MODEL:
        raise LocalSourceError("index_mismatch", "The index does not declare the supported E5 model.")
    dimension = metadata.get("dimension")
    chunks = metadata.get("chunks")
    if (type(dimension) is not int or dimension <= 0 or
            not isinstance(chunks, list) or not chunks):
        raise LocalSourceError("index_mismatch", "Index metadata has invalid dimensions or chunks.")
    chunk_ids: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict) or any(
            not isinstance(chunk.get(key), str) or not chunk[key].strip()
            for key in ("chunk_id", "text", "url")
        ):
            raise LocalSourceError("index_mismatch", "Index metadata contains an invalid chunk.")
        if chunk["chunk_id"] in chunk_ids:
            raise LocalSourceError("index_mismatch", "Index metadata contains duplicate chunk IDs.")
        chunk_ids.add(chunk["chunk_id"])
        if chunk.get("doc_id", chunk["url"]) != chunk["url"]:
            raise LocalSourceError("index_mismatch", "A chunk has inconsistent document identity.")

    try:
        retriever = Retriever(str(directory))
    except ImportError as exc:
        raise LocalSourceError("index_unavailable", "Local vector search dependencies are unavailable.") from exc
    except Exception as exc:
        raise LocalSourceError("index_mismatch", "The local index cannot be loaded consistently.") from exc
    if retriever.index.d != dimension or retriever.index.ntotal != len(chunks):
        raise LocalSourceError("index_mismatch", "Index dimensions or counts do not match metadata.")

    bound = metadata.get("provenance_version") == 1
    if bound:
        if (metadata.get("index_sha256") != hashes[0] or metadata.get("query_prefix") != "query: "
                or metadata.get("passage_prefix") != "passage: " or metadata.get("normalize_embeddings") is not True):
            raise LocalSourceError("index_mismatch", "Index bytes or encoding settings do not match the build record.")
        for field, size in (("corpus_sha256", 64), ("model_revision", 40)):
            value = metadata.get(field)
            if not isinstance(value, str) or len(value) != size or any(c not in "0123456789abcdef" for c in value):
                raise LocalSourceError("index_mismatch", "The build record has an invalid source version.")
        if model_path is None:
            raise LocalSourceError("model_unavailable", "Supply the model folder recorded for this bound index.")
        folder = Path(model_path).resolve()
        expected_files = metadata.get("model_files_sha256")
        if not isinstance(expected_files, dict) or not expected_files:
            raise LocalSourceError("index_mismatch", "Model file hashes are missing from the build record.")
        try:
            for relative, digest in expected_files.items():
                file = (folder / relative).resolve()
                if not file.is_relative_to(folder) or _sha256(file) != digest:
                    raise LocalSourceError("index_mismatch", "The model files differ from the index build.")
        except (OSError, TypeError, ValueError) as exc:
            raise LocalSourceError("model_unavailable", "The bound model files are unavailable.") from exc

    try:
        model = LocalEncoder(str(Path(model_path).resolve()) if model_path else E5_MODEL)
        model_dimension = model.get_sentence_embedding_dimension()
    except Exception as exc:
        raise LocalSourceError("model_unavailable", "The local E5 model or its dependencies are unavailable.") from exc
    if model_dimension != dimension:
        model.close()
        raise LocalSourceError("index_mismatch", "The local E5 model and index have different dimensions.")
    retriever._model = model
    try:
        if hashes != (_sha256(index_path), _sha256(chunks_path)):
            model.close()
            raise LocalSourceError("index_mismatch", "Index files changed while they were being loaded.")
    except OSError as exc:
        raise LocalSourceError("index_unavailable", "Index files became unavailable while loading.") from exc

    versions = {
        "embedding_model": E5_MODEL,
        "embedding_dimension": dimension,
        "index_sha256": hashes[0],
        "chunks_sha256": hashes[1],
        "corpus_sha256": metadata.get("corpus_sha256") if bound else None,
        "model_revision": metadata.get("model_revision") if bound else None,
        "database_chunk_binding": bool(bound and metadata.get("database_chunk_binding")),
    }
    warnings = [
        "The current N3 artifacts do not verify the corpus SHA or model revision.",
        "Artifact hashes identify files; they do not prove N2 acceptance or policy validity.",
    ] if not bound else ["Development index with verified file identities; policy currency and retrieval quality still need review."]
    if metadata.get("over_limit_chunk_ids"):
        warnings.append(f"Upstream chunking exceeds the model token limit in {len(metadata['over_limit_chunk_ids'])} chunks; embeddings may omit tails.")
    return retriever, versions, warnings


def _field(hit: Any, name: str) -> Any:
    return hit.get(name) if isinstance(hit, Mapping) else getattr(hit, name, None)


def validate_hits(db_path: str | Path, hits: Sequence[Any], *, require_chunks: bool = False) -> str | None:
    """Reject stale evidence without dropping or replenishing ranked hits.

    Return the uniform known database corpus SHA, or None if any SHA is unknown.
    This checks database flags, not the unbound N3 index's corpus provenance.
    It never creates a database, changes flags, or writes question/answer logs.
    """
    if not hits:
        return None
    try:
        connection = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise LocalSourceError("database_unavailable", "The document database is unavailable.") from exc
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        known_shas: set[str] = set()
        unknown_sha = False
        for hit in hits:
            doc_id = _field(hit, "doc_id")
            if not isinstance(doc_id, str) or not doc_id or doc_id != _field(hit, "url"):
                raise LocalSourceError("stale_evidence", "Retrieved evidence has invalid document identity.")
            row = connection.execute(
                "SELECT active, index_dirty, corpus_sha256 FROM documents WHERE url = ?",
                (doc_id,),
            ).fetchone()
            if row is None or row[0] != 1 or row[1] != 0:
                raise LocalSourceError(
                    "stale_evidence", "Retrieved evidence is missing, inactive or awaiting reindexing."
                )
            if require_chunks:
                chunk = connection.execute("SELECT doc_id,text FROM chunks WHERE chunk_id=?",
                                           (_field(hit, "chunk_id"),)).fetchone()
                if chunk is None or chunk[0] != doc_id or chunk[1] != _field(hit, "text"):
                    raise LocalSourceError("stale_evidence", "Retrieved chunk text differs from the runtime database.")
            sha = row[2]
            if sha:
                if (not isinstance(sha, str) or len(sha) != 64 or
                        any(character not in "0123456789abcdefABCDEF" for character in sha)):
                    raise LocalSourceError("index_mismatch", "The database has an invalid corpus identity.")
                known_shas.add(sha.lower())
            else:
                unknown_sha = True
        if len(known_shas) > 1:
            raise LocalSourceError("index_mismatch", "Retrieved documents belong to conflicting corpus snapshots.")
        return next(iter(known_shas)) if known_shas and not unknown_sha else None
    except sqlite3.Error as exc:
        raise LocalSourceError("database_unavailable", "The document database cannot validate retrieved evidence.") from exc
    finally:
        connection.close()
