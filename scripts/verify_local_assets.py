"""Verify the member 6 retrieval bundle without loading PyTorch or calling an API."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from scripts.prepare_local_index import verify_snapshot


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def verify(root=Path('.'), *, skip_model=False):
    root = Path(root)
    release = json.loads((root / 'data/release_manifest.json').read_text(encoding='utf-8'))
    for entry in release['files']:
        if digest(root / entry['path']) != entry['sha256']:
            raise ValueError('Published source mismatch: ' + entry['path'])
    _, corpus_sha = verify_snapshot(root / 'data/corpus.jsonl', root / 'data/runtime_indexed.db')
    metadata = json.loads((root / 'data/wsb_index/chunks.json').read_text(encoding='utf-8'))
    if corpus_sha != metadata['corpus_sha256']:
        raise ValueError('Index and runtime database use different corpora')
    if digest(root / 'data/wsb_index/index.faiss') != metadata['index_sha256']:
        raise ValueError('FAISS file differs from the build record')
    if not skip_model:
        model = root / 'data/models/e5-small-614241f'
        if (model / 'REVISION').read_text().strip() != metadata['model_revision']:
            raise ValueError('Model revision mismatch')
        for name, sha in metadata['model_files_sha256'].items():
            if digest(model / name) != sha:
                raise ValueError('Model file mismatch: ' + name)
    conn = sqlite3.connect((root / 'data/runtime_indexed.db').resolve().as_uri() + '?mode=ro', uri=True)
    try:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Runtime database integrity failed')
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Runtime database foreign keys failed')
        rows = {r[0]: r[1:] for r in conn.execute('SELECT chunk_id,doc_id,text FROM chunks')}
        expected = {c['chunk_id']: (c['doc_id'], c['text']) for c in metadata['chunks']}
        if rows != expected:
            raise ValueError('Runtime chunks differ from index metadata')
        indexed = {c['doc_id'] for c in metadata['chunks']}
        states = conn.execute('SELECT url,active,index_dirty FROM documents').fetchall()
        for url, active, dirty in states:
            if active and ((url in indexed and dirty != 0) or (url not in indexed and dirty != 1)):
                raise ValueError('Document index lifecycle mismatch')
    finally:
        conn.close()
    return {'status': 'verified', 'documents': len(states), 'indexed_documents': len(indexed),
            'chunks': len(rows), 'model_checked': not skip_model,
            'corpus_sha256': corpus_sha, 'model_revision': metadata['model_revision'],
            'index_sha256': metadata['index_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-model', action='store_true', help='Check data/index before downloading E5')
    args = parser.parse_args()
    try:
        result = verify(skip_model=args.skip_model)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, 'Asset verification failed: ' + str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
