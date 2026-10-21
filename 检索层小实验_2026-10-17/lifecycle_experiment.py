from pathlib import Path
import sys,sqlite3,json,hashlib
OUT=Path(__file__).resolve().parent; ROOT=OUT.parent
PROJECT=ROOT/'CityU-AgenticRAG-小组作业-成员1集成'
sys.path.insert(0,str(PROJECT))
from src.corpus_import import import_corpus
src=PROJECT/'data/cityu_faq.db'; corpus=PROJECT/'data/corpus.jsonl'
original_sha=hashlib.sha256(src.read_bytes()).hexdigest()
rows=[json.loads(s) for s in corpus.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
target=next(r for r in rows if '/student-visa' in r['url'])
ro=sqlite3.connect(src.resolve().as_uri()+'?mode=ro',uri=True)
mem=sqlite3.connect(':memory:');ro.backup(mem);ro.close()
mem.execute('PRAGMA foreign_keys=ON')
mem.execute('UPDATE documents SET index_dirty=0')
mem.execute('INSERT INTO chunks(chunk_id,doc_id,ord,text) VALUES (?,?,?,?)',('experiment-visa',target['url'],0,'Experiment fixture, not a production chunk'))
mem.commit()
fixture=OUT/'fixtures';fixture.mkdir(exist_ok=True)
reduced=fixture/'snapshot_without_visa.jsonl'
reduced.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows if r['url']!=target['url']),encoding='utf-8')
report=import_corpus(reduced,mem)
state=mem.execute('SELECT active,index_dirty FROM documents WHERE url=?',(target['url'],)).fetchone()
stale=mem.execute('SELECT COUNT(*) FROM chunks c JOIN documents d ON c.doc_id=d.url WHERE d.active=0').fetchone()[0]
active_join=mem.execute('SELECT COUNT(*) FROM chunks c JOIN documents d ON c.doc_id=d.url WHERE d.active=1').fetchone()[0]
assert tuple(state)==(0,1) and stale==1 and active_join==0
first=dict(import_summary={k:report[k] for k in ['input','active_documents','retained_inactive','removed_unreferenced']},retained_document_state={'active':state[0],'index_dirty':state[1]},stale_chunks_without_active_filter=stale,queryable_chunks_with_active_filter=active_join)
# Returning a document must mark it dirty. Index rebuild must compare source version before publishing.
report2=import_corpus(corpus,mem)
second=mem.execute('SELECT active,index_dirty,corpus_sha256 FROM documents WHERE url=?',(target['url'],)).fetchone()
assert tuple(second[:2])==(1,1)
assert hashlib.sha256(src.read_bytes()).hexdigest()==original_sha
result={'fixture':'Production database opened read-only then copied into an in-memory SQLite connection; no FAISS update was executed in this lifecycle control','removed_document':target['url'],'removal':first,'reactivation':{'active':second[0],'index_dirty':second[1],'corpus_sha256':second[2]},'production_db_unchanged':True}
(OUT/'索引生命周期实验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
mem.close()
