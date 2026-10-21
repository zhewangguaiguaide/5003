from pathlib import Path
import json, hashlib, collections, shutil, difflib, re
root = Path.cwd()
before = root/'CityU-AgenticRAG-小组作业-2完成'
after = root/'2修改10-11-7(1)'
out = root/'返工复核_成员2_2026-10-12'
stage = out/'合并验证项目'
changes=[]; diff=[]
for p in sorted(after.rglob('*')):
    if not p.is_file() or '__pycache__' in p.parts: continue
    rel=p.relative_to(after); old=before/rel
    status='added' if not old.exists() else 'same' if old.read_bytes()==p.read_bytes() else 'changed'
    changes.append({'file':str(rel),'status':status})
    if status!='same' and p.suffix in ('.py','.md','.yaml','.sql','.txt'):
        a=old.read_text(encoding='utf-8').splitlines(True) if old.exists() else []
        b=p.read_text(encoding='utf-8').splitlines(True)
        diff.extend(difflib.unified_diff(a,b,fromfile='before/'+str(rel),tofile='after/'+str(rel)))
(out/'代码与文档差异.diff').write_text(''.join(diff),encoding='utf-8')
for name in ['src','tests','docs']:
    for base in [before,after]:
        src=base/name
        if not src.exists(): continue
        for p in src.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.md'):
                dest=stage/p.relative_to(base); dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dest)
for base in [before,after]:
    for name in ['config.yaml','schema.sql','requirements.txt','requirements-lock.txt','README.md','.gitignore']:
        if (base/name).exists(): shutil.copy2(base/name,stage/name)
(stage/'data').mkdir(exist_ok=True)
for p in (after/'data').iterdir():
    if p.is_file(): shutil.copy2(p,stage/'data'/p.name)

def read_rows(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
a=read_rows(before/'data/corpus.jsonl'); b=read_rows(after/'data/corpus.jsonl')
ua={r['url']:r for r in a}; ub={r['url']:r for r in b}
required={'url','title','source','content','date','crawled_at','image_urls','file_urls','error','topic','column','academic_year'}
def summary(rows):
    return {'rows':len(rows),'columns':dict(collections.Counter(r['column'] for r in rows)),
    'chars':sum(len(r['content']) for r in rows),'min_chars':min(len(r['content']) for r in rows),
    'academic_year':dict(collections.Counter(r['academic_year'] for r in rows)),
    'date_is_crawled_at':sum(r['date']==r['crawled_at'] for r in rows),
    'attachments':sum(len(r['file_urls']) for r in rows),
    'schema_errors':[i+1 for i,r in enumerate(rows) if set(r)!=required],
    'empty_required':[i+1 for i,r in enumerate(rows) if any(not r.get(k) for k in ['url','title','source','content','date','crawled_at','topic','column'])],
    'error_rows':sum(bool(r['error']) for r in rows),
    'short_rows':[{'url':r['url'],'chars':len(r['content'])} for r in rows if len(r['content'])<400],
    'duplicate_url':len(rows)-len({r['url'] for r in rows}),
    'duplicate_content':len(rows)-len({re.sub(r'\s+',' ',r['content'].replace('\u00a0',' ')).strip().lower() for r in rows}),
    'replacement_char_rows':sum('\ufffd' in r['content'] for r in rows)}
removed=[{'url':u,'chars':len(ua[u]['content'])} for u in ua.keys()-ub.keys()]
modified=[{'url':u,'old_chars':len(ua[u]['content']),'new_chars':len(ub[u]['content']),
           'changed_fields':[k for k in ua[u] if ua[u][k]!=ub[u][k]]} for u in ua.keys()&ub.keys() if ua[u]!=ub[u]]
q=json.loads((after/'data/quality_report.json').read_text(encoding='utf-8'))
seed_check=[{'url':s['url'],'in_corpus':s['url'] in ub,'reported_chars':s['chars'],
            'actual_chars':len(ub[s['url']]['content']) if s['url'] in ub else None} for s in q['seeds']]
audit=read_rows(after/'data/crawl_audit.jsonl')
audit_summary=[]
for i,x in enumerate(audit):
    events=x.get('events',[])
    audit_summary.append({'line':i+1,'column':x.get('column'),'time':x.get('time'),'events':len(events),
                          'statuses':dict(collections.Counter(e.get('status') for e in events)),
                          'stats':x.get('stats'),
                          'failed_events':[e for e in events if e.get('status')=='error']})
result={'changes':changes,'before':summary(a),'after':summary(b),'removed':removed,
        'added_urls':sorted(ub.keys()-ua.keys()),'modified':modified,'seed_check':seed_check,
        'audit':audit_summary,'corpus_sha256':hashlib.sha256((after/'data/corpus.jsonl').read_bytes()).hexdigest()}
(out/'复核证据.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'changes':changes,'before':result['before'],'after':result['after'],'removed':removed,
'added_count':len(result['added_urls']),'modified_count':len(modified),'seed_check':seed_check,
'audit_summary':[{k:v for k,v in x.items() if k not in ['failed_events','stats']} for x in audit_summary]},ensure_ascii=False,indent=2))
