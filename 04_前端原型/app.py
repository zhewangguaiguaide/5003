#!/usr/bin/env python3
"""Local evidence UI for DSC5003.

Stdlib only. Serves the static frontend and an honest wiring demo that invokes
the frozen R05 backend with its synthetic demo fixture. The full N5/N7 runtime
still requires the model, index and key described in the backend README.
"""
from __future__ import annotations

import argparse
import errno
import json
import mimetypes
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / 'web'
DATA = ROOT / 'data'
DEFAULT_BACKEND = ROOT.parent / '5003_c7b067f'
LEGACY_BACKEND = ROOT.parent / '03_源代码_Git快照' / '5003_c7b067f'

try:
    import evidence_qa
except Exception as _qa_import_error:  # pragma: no cover - surfaced by /api/health
    evidence_qa = None
    _QA_IMPORT_ERROR = str(_qa_import_error)
else:
    _QA_IMPORT_ERROR = None

INDEX = None
INDEX_ERROR = None


def find_backend(explicit: str | None = None) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get('R05_BACKEND_ROOT'):
        candidates.append(Path(os.environ['R05_BACKEND_ROOT']))
    candidates.append(DEFAULT_BACKEND)
    candidates.append(LEGACY_BACKEND)
    for candidate in candidates:
        candidate = candidate.resolve()
        if (candidate / 'src' / 'main.py').is_file() and (candidate / 'src' / 'agentic_rag.py').is_file():
            return candidate
    return None


BACKEND = find_backend()


def get_index():
    global INDEX, INDEX_ERROR
    if INDEX is not None:
        return INDEX
    if evidence_qa is None:
        INDEX_ERROR = _QA_IMPORT_ERROR or 'evidence_qa module unavailable'
        return None
    if BACKEND is None:
        INDEX_ERROR = 'R05 backend snapshot not found.'
        return None
    chunks = BACKEND / 'data' / 'wsb_index' / 'chunks.json'
    if not chunks.is_file():
        INDEX_ERROR = f'Retrieval snapshot not found: {chunks}'
        return None
    try:
        INDEX = evidence_qa.EvidenceIndex(chunks)
    except Exception as exc:
        INDEX_ERROR = str(exc)
        return None
    return INDEX


def json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode('utf-8')



SQL_CASES = {
    'Q1': {
        'sql': "SELECT topic, COUNT(*) AS docs, SUM(CASE WHEN academic_year <> '' THEN 1 ELSE 0 END) AS with_year FROM documents WHERE active=1 GROUP BY topic ORDER BY docs DESC",
        'params': [],
    },
    'Q2': {
        'sql': "SELECT title, academic_year, date FROM documents WHERE active=1 AND topic=? AND academic_year<>'' ORDER BY academic_year DESC,date DESC LIMIT 5",
        'params': ['学费与缴费'],
    },
    'Q3': {
        'sql': 'SELECT url,title,active,index_dirty,corpus_sha256 FROM documents WHERE url=?',
        'params': ['https://www.cityu.edu.hk/admo'],
    },
}


def run_sql_case(query_id: str) -> dict:
    if query_id not in SQL_CASES:
        raise ValueError('Unknown preset query')
    if BACKEND is None:
        raise RuntimeError('R05 backend snapshot not found.')
    db_path = BACKEND / 'data' / 'cityu_faq.db'
    if not db_path.is_file():
        raise RuntimeError('Published SQLite database not found.')
    case = SQL_CASES[query_id]
    started = time.perf_counter()
    with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as conn:
        cursor = conn.execute(case['sql'], case['params'])
        columns = [item[0] for item in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        plans = [row[3] for row in conn.execute('EXPLAIN QUERY PLAN ' + case['sql'], case['params']).fetchall()]
    return {
        'query_id': query_id,
        'sql': case['sql'],
        'params': case['params'],
        'columns': columns,
        'rows': rows,
        'plan': plans,
        'latency_ms': round((time.perf_counter() - started) * 1000, 3),
        'mode': 'read-only',
    }

def run_qa(question: str, topic: str | None, use_llm: bool | None = None) -> dict:
    index = get_index()
    if index is None:
        raise RuntimeError(INDEX_ERROR or 'Evidence index is unavailable.')
    return evidence_qa.ask(index, question, topic=topic, use_llm=use_llm)


def run_backend_demo(question: str, topic: str | None) -> dict:
    if BACKEND is None:
        raise RuntimeError('R05 backend snapshot not found. Set R05_BACKEND_ROOT or pass --backend.')
    command = [sys.executable, '-m', 'src.main', '--ask-local', question,
               '--rag-demo', '--local-mode', 'agentic_rag', '--json']
    if topic:
        command.extend(['--topic', topic])
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    completed = subprocess.run(
        command, cwd=BACKEND, env=env, capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=45, check=False,
    )
    raw = (completed.stdout or '').strip()
    payload = None
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            for line in reversed(raw.splitlines()):
                try:
                    payload = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
    if payload is None:
        detail = (completed.stderr or raw or 'No JSON returned').strip()
        raise RuntimeError(detail[-800:])
    payload['mode'] = 'synthetic'
    payload['synthetic'] = True
    payload['_transport'] = {
        'exit_code': completed.returncode,
        'backend': 'R05 synthetic-demo fixture',
        'synthetic': True,
        'command': 'python -m src.main --ask-local ... --rag-demo --local-mode agentic_rag --json',
    }
    return payload


class Handler(BaseHTTPRequestHandler):
    server_version = 'DSC5003EvidenceUI/1.0'

    def log_message(self, fmt, *args):
        sys.stdout.write('[ui] ' + (fmt % args) + '\n')

    def send_json(self, status: int, value: dict):
        body = json_bytes(value)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/api/health':
            qa_health = evidence_qa.health(get_index()) if evidence_qa else {
                'status': 'module_missing', 'index_ready': False, 'error': _QA_IMPORT_ERROR,
            }
            self.send_json(HTTPStatus.OK, {
                'status': 'ok',
                'backend_found': BACKEND is not None,
                'backend': str(BACKEND) if BACKEND else None,
                'demo': 'synthetic backend fixture',
                'qa': qa_health,
                'qa_error': INDEX_ERROR,
            })
            return
        if parsed.path.startswith('/data/'):
            base = DATA
            relative = urllib.parse.unquote(parsed.path[len('/data/'):])
        else:
            base = WEB
            relative = 'index.html' if parsed.path in ('', '/') else urllib.parse.unquote(parsed.path.lstrip('/'))
        target = (base / relative).resolve()
        try:
            target.relative_to(base.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime, _ = mimetypes.guess_type(target.name)
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', (mime or 'application/octet-stream') + ('; charset=utf-8' if (mime or '').startswith('text/') or mime in ('application/javascript', 'application/json') else ''))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in ('/api/backend-demo', '/api/sql', '/api/answer'):
            self.send_json(HTTPStatus.NOT_FOUND, {'error': 'Unknown endpoint'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 65536:
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length).decode('utf-8'))
            if parsed.path == '/api/sql':
                query_id = body.get('id', '')
                if not isinstance(query_id, str):
                    raise ValueError('Invalid query id')
                self.send_json(HTTPStatus.OK, run_sql_case(query_id))
                return
            if parsed.path == '/api/answer':
                question = body.get('question', '')
                if not isinstance(question, str) or not question.strip() or len(question) > 2000:
                    raise ValueError('Question must be 1-2000 characters.')
                topic = body.get('topic') or None
                if topic is not None and not isinstance(topic, str):
                    raise ValueError('Invalid topic')
                use_llm = body.get('use_llm')
                if use_llm is not None and not isinstance(use_llm, bool):
                    raise ValueError('Invalid use_llm flag')
                self.send_json(HTTPStatus.OK, run_qa(question.strip(), topic, use_llm))
                return
            question = body.get('question', '')
            if not isinstance(question, str) or not question.strip() or len(question) > 2000:
                raise ValueError('Question must be 1–2000 characters')
            topic = body.get('topic') or None
            if topic is not None and not isinstance(topic, str):
                raise ValueError('Invalid topic')
            self.send_json(HTTPStatus.OK, run_backend_demo(question.strip(), topic))
        except subprocess.TimeoutExpired:
            self.send_json(HTTPStatus.GATEWAY_TIMEOUT, {'error': 'Backend demo timed out after 45 seconds.'})
        except Exception as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {'error': str(exc)[:1200]})


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    parser = argparse.ArgumentParser(description='DSC5003 local evidence UI')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, help='Listen port; defaults to the first available port in 8501-8510')
    parser.add_argument('--backend', help='Path to the R05 backend snapshot')
    parser.add_argument('--open', action='store_true', help='Open the browser after starting')
    args = parser.parse_args()
    global BACKEND
    BACKEND = find_backend(args.backend)
    server = None
    for port in ([args.port] if args.port is not None else range(8501, 8511)):
        try:
            server = LocalHTTPServer((args.host, port), Handler)
            break
        except OSError as exc:
            if args.port is not None or (exc.errno != errno.EADDRINUSE and getattr(exc, 'winerror', None) != 10048):
                raise
    if server is None:
        parser.error('No available port in 8501-8510. Pass --port to select another port.')
    url = f'http://{args.host}:{server.server_address[1]}/'
    print(f'DSC5003 Evidence UI: {url}')
    print(f'R05 demo backend: {BACKEND or "not found (snapshot pages still work)"}')
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()


