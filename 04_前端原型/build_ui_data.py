"""Rebuild the frozen evidence view from files inside this submission package."""
import collections, csv, json
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent
BACKEND = FRONTEND.parent / '5003_c7b067f'
EVIDENCE = FRONTEND.parent / '05_评估与数据证据'
R02 = EVIDENCE / '数据质量'
R04 = EVIDENCE / '检索与数据库评估'
R06 = EVIDENCE / '回答质量评估'
OUT = FRONTEND / 'data' / 'ui_data.json'
OUT.parent.mkdir(parents=True, exist_ok=True)

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

chunks_doc = read_json(BACKEND / 'data' / 'wsb_index' / 'chunks.json')
chunks = {c['chunk_id']: c for c in chunks_doc['chunks']}

def hit(score, display_title, chunk_id, topic):
    c = chunks.get(chunk_id)
    if c is None:
        raise KeyError(chunk_id)
    return {
        'score': score,
        'display_title': display_title,
        'topic': topic,
        'chunk_id': chunk_id,
        'source_title': c['title'],
        'url': c['url'],
        'excerpt': ' '.join(c['text'].split())[:520],
        'academic_year': c.get('academic_year') or 'Not recorded',
    }

coverage_rows = read_csv(R02 / '5003_R02_data_栏目覆盖_20261118_v02.csv')
coverage = []
for row in coverage_rows:
    if row['column'] == 'TOTAL':
        continue
    coverage.append({
        'topic_zh': row['topic_zh'], 'topic_en': row['topic_en'],
        'docs': int(row['docs_final']), 'before': int(row['docs_before_rework_20261011']),
        'median_chars': int(row['median_chars']), 'with_year': int(row['docs_with_academic_year']),
    })
funnel_rows = read_csv(R02 / '5003_R02_data_清洗漏斗_20261118_v02.csv')
funnel = [{'stage': r['stage'], 'count': int(r['count']), 'evidence': r['evidence']} for r in funnel_rows]
dedup_rows = read_csv(R02 / '5003_R02_data_去重样例_20261118_v02.csv')
dedup = [{'raw_url': r['raw_url'], 'kept': r['kept_canonical_url'], 'reason': r['reason'], 'chars': int(r['raw_chars'])} for r in dedup_rows[:6]]
filtered_payload = read_json(R02 / '接口样例' / '5003_R02_F2_M1-C_payload_20261118_v02.json')
filtered = filtered_payload['rows']

facts = read_json(EVIDENCE / '数据库与系统核验' / 'facts_verified.json')
schema = read_json(EVIDENCE / '数据库与系统核验' / 'database_schema_actual.json')
sql_cases = read_json(EVIDENCE / '数据库与系统核验' / 'sql_results_and_explain.json')

r04_rows = read_csv(R04 / '5003_R04_data_检索汇总_20261116_v01.csv')
ablation = []
for r in r04_rows:
    ablation.append({
        'configuration': r['configuration'], 'depth': int(r['candidate_depth']),
        'hit1': int(r['hit_at_1_count']), 'hit5': int(r['hit_at_5_count']),
        'hit5_rate': float(r['hit_at_5_rate']), 'mrr5': r['mrr_at_5'],
        'latency_mean': float(r['latency_mean_s']), 'latency_median': float(r['latency_median_s']), 'latency_p95': float(r['latency_p95_s']),
        'status': r['status'],
    })
failure_rows = read_csv(R04 / '5003_R04_data_逐题失败_20261116_v01.csv')
r4_failures = [{
    'case_id': r['case_id'], 'topic': r['topic'],
    'query': 'Controlled CORE20 item — query withheld from public UI',
    'query_redacted': True, 'reason': r['failure_reasons'],
} for r in failure_rows]
yp = read_json(R06 / 'yp_run_summary.json')

faiss_hits = [
    hit(0.8970, 'Admission FAQ: tuition payment timing', 'https://www.cityu.edu.hk/admo/faq#chunk-162', 'Admission'),
    hit(0.8746, 'Finance Office: tuition-fee liability', 'https://www.cityu.edu.hk/fo/htm/tuition_fees.htm#chunk-0', 'Tuition & payment'),
    hit(0.8745, 'Finance Office: payment schedule', 'https://www.cityu.edu.hk/fo/htm/Degree_PaySchedule.htm#chunk-0', 'Tuition & payment'),
    hit(0.8727, 'Admission FAQ: timetable clash (off-topic)', 'https://www.cityu.edu.hk/admo/faq#chunk-167', 'Admission'),
    hit(0.8720, 'Finance Office: payment schedule', 'https://www.cityu.edu.hk/fo/htm/TPg_PaySchedule.htm#chunk-0', 'Tuition & payment'),
]
rerank_hits = [
    hit(2.2564, 'Admission FAQ: tuition payment timing', 'https://www.cityu.edu.hk/admo/faq#chunk-162', 'Admission'),
    hit(1.0782, 'Finance Office: payment schedule', 'https://www.cityu.edu.hk/fo/htm/Degree_PaySchedule.htm#chunk-0', 'Tuition & payment'),
    hit(0.9936, 'Finance Office: payment schedule', 'https://www.cityu.edu.hk/fo/htm/Degree_PaySchedule.htm#chunk-1', 'Tuition & payment'),
    hit(0.9312, 'Finance Office: fees and charges', 'https://www.cityu.edu.hk/fo/htm/degree_fees.htm#chunk-0', 'Tuition & payment'),
    hit(0.5232, 'Finance Office: fees and charges', 'https://www.cityu.edu.hk/fo/htm/degree_fees.htm#chunk-1', 'Tuition & payment'),
]
failure_faiss = hit(0.8709, 'Research Impact guide', 'https://libguides.library.cityu.edu.hk/research_impact#chunk-0', 'Library')
failure_rerank = hit(-1.0872, 'Why CityUHK admissions page', 'https://www.cityu.edu.hk/admo/why-cityuhk#chunk-0', 'Admission')

pay_citations = []
for sid, cid in zip(['S11','S12','S13'], ['https://www.cityu.edu.hk/fo/htm/paymethods.htm#chunk-1', 'https://www.cityu.edu.hk/fo/htm/paymethods.htm#chunk-2', 'https://www.cityu.edu.hk/fo/htm/paymethods.htm#chunk-5']):
    c = chunks[cid]
    pay_citations.append({'source_id': sid, 'title': c['title'], 'url': c['url'], 'chunk_id': cid,
                          'excerpt': ' '.join(c['text'].split())[:420]})


corpus_rows = [json.loads(line) for line in (BACKEND / 'data' / 'corpus.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
sample_docs = []
preferred = {
    '申请': '/admo/faq', '校历与重要日期': '/arro/impd',
    '学费与缴费': '/fo/htm/paymethods', '图书馆': 'libguides.library.cityu.edu.hk/start',
    '注册与学籍': '/arro/creg/creg_main', '宿舍': '/sro/StudentHousing',
    '奖学金与助学金': 'scholarships-prizes-at-a-glance',
    '签证与国际学生服务': '/geo/non-local-students',
}
by_topic = {}
for row in corpus_rows:
    by_topic.setdefault(row.get('topic') or '', []).append(row)
for topic, items in by_topic.items():
    chosen = next((r for r in items if preferred.get(topic, '__none__') in (r.get('url') or '')), None)
    if chosen is None:
        chosen = max(items, key=lambda r: len(r.get('content') or ''))
    sample_docs.append({
        'topic': topic,
        'title': chosen.get('title') or '',
        'url': chosen.get('url') or '',
        'academic_year': chosen.get('academic_year') or '',
        'chars': len(chosen.get('content') or ''),
    })
doc_chunk_map = {}
for chunk in chunks_doc.get('chunks') or []:
    doc_chunk_map.setdefault(chunk.get('doc_id', ''), []).append(chunk)
for sample in sample_docs:
    related = doc_chunk_map.get(sample['url'], [])
    sample['indexed_chunks'] = len(related)
    sample['first_chunks'] = [c.get('chunk_id', '') for c in related[:2]]
    sample['first_excerpt'] = (related[0].get('text', '')[:260] if related else '')

rubric = read_json(BACKEND / 'evals' / 'rubric.json')
gold_root = EVIDENCE / '评测金标_私有勿公开上传'
def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
gold_core = read_jsonl(gold_root / '5003_R04_data_gold_CORE20_20261116_v01.jsonl')
gold_dev = read_jsonl(gold_root / '5003_R04_data_gold_R4DEV_20261116_v01.jsonl')
def gold_summary(rows):
    return {
        'rows': len(rows),
        'required_facts': sum(len(r.get('required_facts') or []) for r in rows),
        'gold_evidence': sum(len(r.get('gold_evidence') or []) for r in rows),
        'answerable': sum(1 for r in rows if r.get('answerability') == 'answerable'),
        'review_status': dict(collections.Counter(r.get('review_status') for r in rows)),
        'human_reviewed': dict(collections.Counter(bool(r.get('human_reviewed')) for r in rows)),
        'synthetic': dict(collections.Counter(bool(r.get('synthetic')) for r in rows)),
    }
gold_samples = [
    {
        'id': 'SYNTH-001', 'query': 'Synthetic structure example — not a real CORE20 question',
        'required_facts': ['A necessary fact stated in the source passage.'],
        'required_facts_meta': [{'id': 'f1', 'text': 'A necessary fact stated in the source passage.', 'critical': True}],
        'gold_evidence': [{
            'id': 'e1', 'doc_id': 'example.invalid/synthetic-source', 'locator': 'synthetic locator',
            'quote': 'Synthetic placeholder quote used only to explain the schema.', 'fact_ids': ['f1'],
        }],
        'sufficient_evidence_sets': [['e1']], 'forbidden_claims': ['synthetic forbidden claim'],
        'answerability': 'answerable', 'synthetic': True,
        'review_status': 'schema-demo', 'human_reviewed': False, 'redacted': True,
    },
    {
        'id': 'SYNTH-002', 'query': 'Synthetic calibration example — not a real R4DEV question',
        'required_facts': ['A second fact used for calibration only.'],
        'required_facts_meta': [{'id': 'f1', 'text': 'A second fact used for calibration only.', 'critical': False}],
        'gold_evidence': [{
            'id': 'e1', 'doc_id': 'example.invalid/synthetic-calibration', 'locator': 'synthetic locator',
            'quote': 'Synthetic calibration quote; no school policy is represented.', 'fact_ids': ['f1'],
        }],
        'sufficient_evidence_sets': [['e1']], 'forbidden_claims': [],
        'answerability': 'clarify', 'synthetic': True,
        'review_status': 'schema-demo', 'human_reviewed': False, 'redacted': True,
    },
]

vector_samples = []
for index, chunk in enumerate(chunks_doc['chunks'][:3]):
    vector_samples.append({
        'sample': index + 1, 'faiss_id': index, 'chunk_id': chunk.get('chunk_id', ''),
        'title': chunk.get('title', ''), 'topic': chunk.get('topic', ''),
        'url': chunk.get('url', ''), 'excerpt': (chunk.get('text') or '')[:220],
    })

data = {
    'meta': {
        'project': 'CityU Student Services Evidence Lab', 'course': 'DSC5003',
        'prepared': '2026-11-21', 'deadline': '2026-12-06 23:59',
        'corpus_sha256': facts['corpus_sha256'], 'database_sha256': facts['database_sha256'],
        'repo': 'https://github.com/zhewangguaiguaide/5003',
        'commits': {'backend': 'c7b067f', 'retrieval_eval': '9de28ad', 'agent_eval': '39a1f81'},
        'documents': facts['documents'], 'topics': len(facts['topic_counts']),
        'chunks': len(chunks), 'dimension': chunks_doc['dimension'],
        'mode_notice': 'Frozen evidence and recorded metadata are shown by default. Live buttons run only the synthetic backend demo unless the full model environment is configured.',
    },
    'f1': {
        'recorded': {
            'label': 'N7 DEV replay · 2026-11-19',
            'question': 'How do I pay my tuition?',
            'status': 'answered', 'stop_reason': 'evidence_sufficient',
            'latency_ms': 21853, 'retrieval_rounds': 3, 'llm_calls': 4,
            'total_tokens': 26018, 'usage_note': 'Prompt + completion tokens across the recorded run.',
            'citations': pay_citations,
            'note': 'The public Git snapshot records status, counts and citation IDs; the private answer text and raw trace remain in the ignored run directory. This is not a new execution.',
        },
        'samples': [
            {'id': 'tuition', 'label': 'Tuition payment', 'question': 'How do I pay my tuition?', 'topic': 'fees'},
            {'id': 'library', 'label': 'Library access', 'question': 'What do I need to enter the library?', 'topic': 'library'},
            {'id': 'clarify', 'label': 'Need clarification', 'question': 'Can I get a refund?'},
        ],
        'status_legend': [
            ['answered', 'Evidence supports every requested fact.'],
            ['clarify', 'A user condition is required before retrieval.'],
            ['abstained', 'The available evidence cannot support a complete answer.'],
            ['generation_error', 'Model or backend failed; no answer published.'],
            ['no_evidence', 'No relevant chunks were returned.'],
            ['retrieval_error', 'The retriever or source validation failed.'],
            ['invalid_response', 'The model output failed the contract.'],
            ['source_mismatch', 'Evidence version changed before publication.']
        ],
    },
    'f2': {
        'kpis': [
            {'label': 'Active documents', 'value': facts['documents'], 'note': 'corpus.jsonl = documents'},
            {'label': 'Topics', 'value': '8 / 8', 'note': '13 / 13 configured seeds'},
            {'label': 'Median document', 'value': '2,905', 'note': 'characters'},
            {'label': 'Content duplicates removed', 'value': '23', 'note': 'normalized-content fingerprint'},
        ],
        'coverage': coverage,
        'funnel': funnel,
        'dedup': dedup,
        'filtered': filtered,
        'database': {
            'tables': [
                {'name': k, 'rows': v.get('rows', 0), 'columns': len(v.get('columns', []))}
                for k, v in schema.items()
            ],
            'facts': {
                'schema_columns': 14, 'json_fields': 12, 'indexes': 5,
                'foreign_key': 'chunks.doc_id → documents.url (nullable)',
                'integrity': facts['integrity_check'], 'foreign_key_check': 'empty',
                'with_year': facts['with_academic_year'], 'without_year': facts['without_academic_year'],
            },
            'queries': [
                {'id': qid, 'sql': q['sql'], 'parameters': q.get('parameters', []), 'rows': q['rows'], 'explain': [e['detail'] for e in q['explain']]}
                for qid, q in sql_cases.items()
            ],
            'normalization_note': 'SQLite is the source-document store; FAISS is a derived index. SHA fields are logical provenance, not a foreign key, and the schema does not prove full 3NF.',
        },
        'knowledge_base': {
            'documents': len(corpus_rows), 'topics': len(coverage), 'records': 83,
            'published_chunks': 0, 'runtime_chunks': 881, 'comparison_chunks': 863,
            'indexed_documents': len(doc_chunk_map), 'unindexed_documents': len(set(r.get('url') for r in corpus_rows) - set(doc_chunk_map)),
            'unindexed_ids': chunks_doc.get('unindexed_document_ids') or [],
            'corpus_sha256': facts['corpus_sha256'], 'database_sha256': facts['database_sha256'],
            'sample_docs': sample_docs,
            'field_mapping': [
                ['corpus.jsonl.title', 'documents.title', '页面标题'],
                ['corpus.jsonl.url', 'documents.url / doc_id', '规范URL；chunk与引用共用'],
                ['corpus.jsonl.topic', 'documents.topic', '8主题之一'],
                ['corpus.jsonl.content', 'documents.content', '正文；切块来源'],
                ['corpus.jsonl.column', 'documents.column_name', '配置栏目'],
                ['import adds', 'active / index_dirty / corpus_sha256', '导入与版本状态'],
            ],
            'snapshot_receipt': {
                'version': 'cityu-corpus-159-20261031', 'released_on': '2026-10-31',
                'status': 'development_baseline', 'policy_currency': 'not_certified',
                'human_semantic_acceptance': 'recorded_separately', 'integrity': 'ok', 'foreign_key_errors': 0,
            },
            'chunk_policy': 'documents → runtime chunks (881) → vector rows (384-d) → citations; published SQLite chunks=0; FAISS is a derived index, not a SQLite table.',
        },
    },
    'f3': {
        'query': 'How can I pay my tuition fees?',
        'topic': 'No topic filter, matching the R03 frozen run',
        'faiss': faiss_hits, 'rerank': rerank_hits,
        'failure': {
            'query': '进入图书馆需要什么证件？',
            'faiss': failure_faiss, 'rerank': failure_rerank,
            'conclusion': 'Top-1 shown; R03 records no direct answer in either Top-5. Reranking is not a universal fix.',
        },
        'index': {
            'chunks': 863, 'vectors': 863, 'dimension': chunks_doc['dimension'],
            'embedding': chunks_doc['model'], 'rerank': 'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1',
            'index_type': 'FAISS IndexFlatIP', 'prefixes': 'query: / passage:',
            'model_revision': chunks_doc.get('model_revision'),
            'index_sha256': chunks_doc.get('index_sha256'),
            'corpus_sha256': chunks_doc.get('corpus_sha256'),
            'provenance_version': chunks_doc.get('provenance_version'),
            'runtime_chunks': 881, 'comparison_chunks': 863,
            'vector_samples': vector_samples,
            'build_receipt': {
                'normalize_embeddings': chunks_doc.get('normalize_embeddings'),
                'max_seq_length': chunks_doc.get('max_seq_length'),
                'source_database_sha256': chunks_doc.get('source_database_sha256'),
                'database_chunk_binding': chunks_doc.get('database_chunk_binding'),
                'device': chunks_doc.get('device'), 'encoder_process': chunks_doc.get('encoder_process'),
                'created_at_utc': chunks_doc.get('created_at_utc'),
                'unindexed_document_ids': chunks_doc.get('unindexed_document_ids') or [],
            },
            'mapping': 'FAISS row (0-based) → chunk_id → doc_id/url → excerpt',
        },
        'source_note': 'Scores and titles follow the R03 863-chunk comparison; URLs and excerpts are resolved to matching chunks in the R05 881-chunk snapshot for inspection. The excerpt snapshot is not the same build as the 863 score run; FAISS and rerank scales are also different.',
    },
    'f4': {
        'core': {
            'title': 'R4-CORE20 · retrieval only',
            'denominator': 20, 'metric': 'Hit@5', 'selected': 'E5 + rerank@50',
            'selected_count': 17, 'status': 'draft_retrieval_only',
            'ablation': ablation,
            'failures': r4_failures,
            'note': '17/20 is evidence retrieval, not answer accuracy. Questions and the answer key are now public, so this is not a private held-out set.',
        },
        'agent': {
            'title': 'R6-YP-CORE20 · N5 one-pass + AI provisional review',
            'denominator': 20, 'retrieval_hit5': yp['retrieval']['hit_at_5']['count'],
            'answered': yp['core_response_statuses']['answered'], 'abstained': yp['core_response_statuses']['abstained'],
            'pass': yp['core_ai_provisional']['pass'], 'fail': yp['core_ai_provisional']['fail'],
            'pending': yp['core_ai_provisional']['pending_gold_scope'],
            'nonretrieval_safe': yp['nonretrieval_ai_provisional']['safe'],
            'nonretrieval_full_action': yp['nonretrieval_ai_provisional']['fully_meets_expected_action'],
            'hard_fail_candidates': yp['core_ai_provisional'].get('hard_fail_candidates', 0),
            'note': 'AI review is provisional. 15/20 belongs to a different set from R4 CORE20 and cannot be plotted as a rerank comparison.',
            'manual_pass': 15, 'manual_fail': 5,
            'manual_note': 'R06 manual adjudication: 15 pass / 5 fail; 2 cases manually adjudicated, 18 remain AI-only; independent double review is pending.',
        },
        'db': {
            'title': 'Database workload supplement',
            'source': 'R01 supplemental local experiment; role4 independent acceptance remains pending',
            'rows': [
                {'scale': '159 rows', 'query': 'Q2 topic + nonempty-year ordering', 'no_index': 0.014837, 'indexed': 0.006329, 'no_index_p95': 0.015601, 'indexed_p95': 0.006527},
                {'scale': '1,590 rows (10x synthetic)', 'query': 'Q2 topic + nonempty-year ordering', 'no_index': 0.117979, 'indexed': 0.009732, 'no_index_p95': 0.157803, 'indexed_p95': 0.010492},
                {'scale': '1,590 rows (10x synthetic)', 'query': 'Q1 grouped count', 'no_index': 0.301425, 'indexed': 0.308736, 'no_index_p95': 0.366181, 'indexed_p95': 0.390746},
            ],
            'method': 'In-memory read-only copies; 20 warm-ups, 101 paired batches, 100 execute+fetchall per batch. No-index/Indexed columns are medians; p95 is of batch means, not request-level tail latency.',
            'takeaway': 'Q2 improves; Q1 is a counterexample. Do not call every query faster.',
        },
        'usability': {
            'status': 'not_run',
            'plan': '3–5 users × 5 tasks: fees, visa, calendar, FAQ, unsupported/personal-state',
            'note': 'The template exists, but no sessions, success rate or Likert result are claimed.',
        },
        'rubric': {
            'version': rubric.get('version'), 'status': rubric.get('status'),
            'owner_role': rubric.get('owner_role'), 'reviewer_role': rubric.get('reviewer_role'),
            'dimensions': rubric.get('dimensions') or [],
            'hard_fail_conditions': rubric.get('hard_fail_conditions') or [],
            'scoring_rules': rubric.get('scoring_rules') or [],
            'retrieval_rules': rubric.get('retrieval_rules') or {},
        },
        'gold': {
            'core': gold_summary(gold_core), 'dev': gold_summary(gold_dev),
            'samples': gold_samples,
            'note': 'The actual CORE20/R4DEV gold JSONL is controlled and is not shipped to the public UI. The UI shows aggregate counts and synthetic schema examples only.',
        },
        'boundaries': [
            'Retrieval evidence, answer status and provisional task judgment measure different things.',
            'R04 formal DB performance and usability study are not run; the table is an R01 supplemental in-memory experiment, not independent acceptance.',
            'No formal answer accuracy or N7 acceptance result is claimed.',
        ],
    },
    'f5': {
        'team': [
            ['① 组长', 'Integration, frontend, database design, demo'],
            ['② 王尔卓', 'Collection, cleaning, data quality, F1/F2/F3'],
            ['③ 王嘉一', 'Chunking, embedding, FAISS retrieval, F3'],
            ['④ 韩上', 'Retrieval and database evaluation, F4'],
            ['⑤ 张宏扬', 'Query adaptation, N5/N7 backend, API'],
            ['⑥ 柯燕萍', 'Agent rubric, CORE review, failure analysis'],
        ],
        'commands': [
            {'label': 'Launch UI', 'command': 'python app.py --open'},
            {'label': 'Health check', 'command': 'Invoke-RestMethod http://127.0.0.1:8501/api/health'},
            {'label': 'Backend demo (no key)', 'command': 'python -m src.main --ask-local "How do I pay my tuition?" --rag-demo --local-mode agentic_rag --json'},
            {'label': 'Real N5/N7 (881 snapshot; model + key required)', 'command': 'python -m src.main --ask-local "How do I pay my tuition?" --index-dir data/wsb_index --db data/runtime_indexed.db --local-mode agentic_rag --json'},
            {'label': 'Database status', 'command': 'python -m src.main --db data/runtime_indexed.db --status'},
        ],
        'architecture': [
            ['01', 'F1–F5 UI', 'question, evidence, database, evaluation, delivery'],
            ['02', 'CLI / HTTP adapter', 'ask-local JSON; citations and status'],
            ['03', 'N5 / N7', 'one-pass RAG or bounded agentic loop'],
            ['04', 'FAISS + SQLite', 'R03 comparison: 863 chunks; R05 runtime: 881 chunks; documents and runtime checks'],
            ['05', 'JSONL corpus', '159 active CityU documents, SHA-bound'],
        ],        'deliverables': [
            ['Group information', 'Names, undergraduate majors, roles and contribution text', 'Pending confirmation'],
            ['Source code', 'GitHub branch snapshot c7b067f + this frontend', 'Available locally'],
            ['Final report PDF', 'Merge member chapters and export XXXX-report.pdf', 'Not yet merged'],
            ['Video 5–8 min', 'Record UI, query execution, data flow and backend', 'Not yet recorded'],
            ['Working video link', 'Google Drive / OneDrive / Dropbox', 'Pending upload'],
        ],
    },
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'output': str(OUT), 'bytes': OUT.stat().st_size, 'f3_chunks': len(faiss_hits), 'coverage': len(coverage)}, ensure_ascii=False))



