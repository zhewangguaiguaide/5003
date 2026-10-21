from pathlib import Path
import sys,json,re,sqlite3,collections,importlib.metadata
root=Path(__file__).resolve().parent.parent
out=Path(__file__).resolve().parent
sys.path.insert(0,str(out/'合并验证项目'))
from src.storage import Record
from src.parser import is_navigation_only
from src.corpus import infer_academic_year,deduplicate
from src.db import init_schema,migrate_from_records
load=lambda p:[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
a=load(root/'CityU-AgenticRAG-小组作业-2完成/data/corpus.jsonl')
b=load(root/'2修改10-11-7(1)/data/corpus.jsonl')
rows=[Record(**{k:v for k,v in x.items() if k!='academic_year'}) for x in b]
contact=next(x for x in a if 'NSY/contactus' in x['url'])
nav=next(x for x in b if x['url'].endswith('/explore/news-and-events'))
conn=sqlite3.connect(':memory:');init_schema(conn)
empty=migrate_from_records([],conn)
full=migrate_from_records(rows,conn)
conn.execute("INSERT INTO documents(url,content) VALUES('https://old.example/removed','old')")
conn.execute("INSERT INTO chunks(chunk_id,doc_id,ord,text) VALUES('old-chunk','https://old.example/removed',0,'old')")
retained=migrate_from_records(rows,conn)
old_db=root/'CityU-AgenticRAG-小组作业-2完成/data/cityu_faq.db'
with sqlite3.connect(old_db.as_uri()+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    records=[]
    for rr in db.execute('SELECT * FROM records'):
        d=dict(rr);d['column']=d.pop('column_name')
        for k in ['image_urls','file_urls']:d[k]=json.loads(d[k] or '[]')
        records.append(Record(**d))
old_reexport=deduplicate(records)[1]
lock=[]
for line in (root/'2修改10-11-7(1)/requirements-lock.txt').read_text(encoding='utf-8').splitlines():
    if '==' not in line:continue
    name,wanted=line.split('==',1)
    try:found=importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:found=None
    lock.append({'package':name,'expected':wanted,'actual':found,'match':wanted==found})
result={'year_false_matches':[
{'url':x['url'],'exported':x['academic_year'],'recomputed':infer_academic_year(Record(**{k:v for k,v in x.items() if k!='academic_year'}))}
for x in b if x['academic_year'] in ['2026-2021','2025-2028']],
'cleaning':{'useful_contact_url':contact['url'],'useful_contact_chars':len(contact['content']),
'useful_contact_classified_navigation':is_navigation_only(contact['content']),
'useful_contact_filtered':len(deduplicate([Record(**{k:v for k,v in contact.items() if k!='academic_year'})])[0])==0,
'news_navigation_url':nav['url'],'news_navigation_chars':len(nav['content']),
'news_navigation_classified_navigation':is_navigation_only(nav['content'])},
'database':{'empty_records_migration_documents':empty['documents'],
'new_corpus_converted_to_records_migration_documents':full['documents'],
'migration_with_old_referenced_document':retained['documents'],
'old_database_reexport_under_new_code':old_reexport,
'documents_columns':[x[1] for x in conn.execute('PRAGMA table_info(documents)')]},
'validation_environment':{'python':sys.version,'executable':sys.executable,'lock_comparison':lock}}
(out/'边界问题复现.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='validation_environment'},ensure_ascii=True,indent=2))
print('LOCK_MATCH',sum(x['match'] for x in lock),len(lock))
