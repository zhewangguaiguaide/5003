"""Small offline controls, not a BGE-M3 quality benchmark. Source project is read-only."""
from pathlib import Path
from collections import Counter,defaultdict
import sys,json,re,hashlib,sqlite3,time,platform,statistics,os
OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
PROJECT=ROOT/'CityU-AgenticRAG-小组作业-成员1集成'
sys.path.insert(0,str(OUT/'.deps'))
import numpy as np
import faiss
faiss.omp_set_num_threads(1)
CORPUS=PROJECT/'data/corpus.jsonl'
DB=PROJECT/'data/cityu_faq.db'
SOURCE_FILES=[CORPUS,DB,PROJECT/'data/quality_documents.json']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
BEFORE={str(p.relative_to(ROOT)):sha(p) for p in SOURCE_FILES}
rows=[json.loads(s) for s in CORPUS.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
TOKEN=re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*|\d+(?:[,./:]\d+)*|[^\w\s]",re.UNICODE)
def offsets(text): return [(m.start(),m.end()) for m in TOKEN.finditer(text)]
def count(text): return len(offsets(text))
def window_ranges(text,size,overlap,base=0):
    tok=offsets(text); out=[]
    for a in range(0,len(tok),size-overlap):
        b=min(a+size,len(tok)); out.append((base+tok[a][0],base+tok[b-1][1]))
        if b==len(tok): break
    return out

def findspan(i,start,end,kind,query,label):
    text=rows[i]['content']; a=text.index(start); b=text.index(end,a)+len(end)
    return dict(id=f'p{len(GOLD)+1:02d}',doc=i,start=a,end=b,kind=kind,query=query,label=label,quote=text[a:b])
GOLD=[]
def add(*args): GOLD.append(findspan(*args))
# Development probes chosen before running any chunking or ranking. Not held-out evaluation.
add(42,'Local\nStudents*','2026 / 27 $47,000','fee','What is the local undergraduate annual tuition fee for 2026/27?','Local 2026/27 tuition')
add(42,'Local\nStudents not Eligible','2026 $392,000 $190,000','fee','What is the 2026 admitted non-local undergraduate tuition fee for other programmes?','Non-local 2026 fee with column headers')
add(42,'1. Graduation Fee 1','(payable upon enrolment) $400','fee','How much is the graduation fee payable upon enrolment?','Graduation fee')
add(42,'4. Late Payment Charge 4','2% on outstanding balance','fee','How much is the late payment charge for overdue fees?','Late payment percentage')
add(42,'10. Replacement of Student ID Card','$100','fee','What is the fee to replace a student ID card?','Student ID replacement')
add(21,'Application Timeline','8 weeks or longer','visa','How long may a student visa application take?','Visa processing duration')
add(21,'Administrative Fee','HKD 600','visa','How much is the student visa application administrative fee?','Visa administrative fee')
add(32,'12 January 2026','Due date for Semester B’s tuition fees','date','When do Semester B classes begin in January 2026?','January Semester B start and tuition due')
add(32,'31 August 2026','Due date for Semester A’s tuition fees','date','When do Semester A classes begin in August 2026?','August Semester A start and tuition due')
add(107,'Counter Services','Closed','hours','What are the Student Residence Office counter service hours on weekdays?','Counter office days and hours')
add(127,'Hall Lodging Fees (HK$)','(per year per person) Double Room: $20,800','fee','What is the annual double room lodging fee at Ma On Shan for new non-local students?','MOS room type fee and unit')
add(127,'Application Period','30 June 2026 (23:59 HKT)','date','When does the 2026/27 new non-local Ma On Shan hall application close?','MOS application window')
add(30,'I have just added/dropped a course today.','worksheet tomorrow.','faq','When will an added or dropped course be reflected in DegreeWorks?','DegreeWorks question plus full answer')
add(30,'What is meant by catalogue term?','discuss with your advisor immediately.','faq','What does catalogue term mean in DegreeWorks?','Catalogue term question plus full answer')
(OUT/'开发探针.json').write_text(json.dumps(GOLD,ensure_ascii=False,indent=2),encoding='utf-8')

DATE=re.compile(r'^(?:From\s+)?\d{1,2}(?:\s*[–-]\s*\d{1,2})?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\b',re.I)
HEADINGS={'Application Timeline','Administrative Fee','What Happens Next','Submission of Required Documents','Counter Services','Address','Phone','Email','Fax','Residential Period','Application Period','Hall Lodging Fees (HK$)','Important Notes','Fees and Charges','Tuition Fees','Self-financed Rate','Notes:'}

def units(i,text,bind_labels=False):
    lines=list(re.finditer(r'[^\n]+(?:\n|$)',text)); ranges=[]; j=0
    while j<len(lines):
        m=lines[j]; line=m.group().strip(); k=j+1
        # Questions can include a question mark before their final sentence.
        isq='?' in line and len(line)<600 and not line.startswith(('http','mailto'))
        if isq:
            while k<len(lines):
                nxt=lines[k].group().strip()
                if ('?' in nxt and len(nxt)<600) or nxt in HEADINGS: break
                k+=1
        elif DATE.match(line):
            while k<len(lines):
                nxt=lines[k].group().strip()
                if DATE.match(nxt) or nxt in HEADINGS or re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}$',nxt): break
                k+=1
        elif line in HEADINGS or re.match(r'^\d+\.\s+\S',line):
            while k<len(lines) and k<j+7:
                nxt=lines[k].group().strip()
                if nxt in HEADINGS or (DATE.match(nxt) and not (bind_labels and line in {'Application Period','Residential Period'} and k==j+1)) or re.match(r'^\d+\.\s+\S',nxt): break
                k+=1
        ranges.append((m.start(),lines[k-1].end())); j=k
    # Finance tables need source header and rows to stay together. Heuristic from labels, not probe coordinates.
    if '/fo/' in rows[i]['url']:
        for start,end in [('Local\nStudents*','Local\nStudents not Eligible'),('Local\nStudents not Eligible','*If there are')]:
            if start in text and end in text:
                a=text.index(start); b=text.index(end,a)
                kept=[]
                for u,v in ranges:
                    if v<=a or u>=b: kept.append((u,v))
                    else:
                        if u<a: kept.append((u,a))
                        if v>b: kept.append((b,v))
                ranges=kept+[(a,b)]
    return sorted(ranges)

def structured(i,text,size=500,overlap=80,bind_labels=False):
    atoms=[]
    for a,b in units(i,text,bind_labels):
        if count(text[a:b])>size:
            atoms.extend(window_ranges(text[a:b],size,overlap,a))
        else: atoms.append((a,b))
    out=[]; start=None; end=None
    for a,b in atoms:
        if start is None: start,end=a,b
        elif count(text[start:b])<=size: end=b
        else:
            out.append((start,end)); start,end=a,b
    if start is not None: out.append((start,end))
    return out

CONFIGS=[('fixed_300_40',300,40),('fixed_500_0',500,0),('fixed_500_80',500,80),('fixed_800_80',800,80),('structure_500_80',500,80),('structure_v2_500_80',500,80)]
CHUNKS={}; stats=[]; spans=[]
for name,size,ov in CONFIGS:
    chunks=[]
    for i,row in enumerate(rows):
        text=row['content']
        rr=structured(i,text,size,ov,bind_labels="v2" in name) if name.startswith('structure') else window_ranges(text,size,ov)
        for ordinal,(a,b) in enumerate(rr):
            chunk_id=hashlib.sha256(f'{sha(CORPUS)}|{name}|{row["url"]}|{a}:{b}'.encode()).hexdigest()[:24]
            chunks.append(dict(id=chunk_id,doc=i,ord=ordinal,start=a,end=b,text=text[a:b]))
    CHUNKS[name]=chunks
    uncovered=0
    for di,row in enumerate(rows):
        cc=[c for c in chunks if c['doc']==di]
        for a,b in offsets(row['content']):
            if not any(c['start']<=a and c['end']>=b for c in cc): uncovered+=1
    assert uncovered==0,(name,uncovered)
    lengths=[count(c['text']) for c in chunks]
    coverage=[]
    for probe in GOLD:
        contained=[c['id'] for c in chunks if c['doc']==probe['doc'] and c['start']<=probe['start'] and c['end']>=probe['end']]
        coverage.append(bool(contained)); spans.append(dict(config=name,probe=probe['id'],preserved=bool(contained),chunk_ids=contained))
    stats.append(dict(config=name,chunks=len(chunks),uncovered_proxy_units=uncovered,proxy_units=sum(lengths),expansion=round(sum(lengths)/sum(count(r['content']) for r in rows),4),p50=float(np.percentile(lengths,50)),p95=float(np.percentile(lengths,95)),maximum=max(lengths),probes_preserved=sum(coverage),probes_total=len(GOLD),vector_payload_1024_float32_mib=round(len(chunks)*1024*4/1024**2,3),failed=[p['id'] for p,b in zip(GOLD,coverage) if not b]))

# Repeat-lines audit: diagnostic only; frequent legitimate policy facts must not be deleted automatically.
line_docs=defaultdict(set)
for i,r in enumerate(rows):
    for line in set(r['content'].splitlines()):
        t=' '.join(line.split())
        if t and len(t)<=120: line_docs[t].add(i)
repeated=[dict(text=t,document_count=len(ids)) for t,ids in line_docs.items() if len(ids)>=10]
repeated.sort(key=lambda x:(-x['document_count'],x['text']))
fee=rows[42]['content']; marker='Fees and Charges\n1.\nTuition Fees'; a=fee.index(marker)
nav_audit=dict(fee_doc=rows[42]['url'],prefix_proxy_units=count(fee[:a]),total_proxy_units=count(fee),prefix_fraction=round(count(fee[:a])/count(fee),4),marker=marker,repeated_short_lines_ge10=len(repeated),examples=repeated[:25])
# FAQ boundaries: whole Q+A is sometimes bigger than a normal budget; no strategy guarantees it will fit.
faq_spans=[]
for i,r in enumerate(rows):
    text=r['content']; qs=[m for m in re.finditer(r'^.*\?.*$',text,re.M) if len(m.group())<600 and not m.group().startswith('http')]
    for q,nxt in zip(qs,qs[1:]):
        n=count(text[q.start():nxt.start()]); faq_spans.append(dict(doc=i,proxy_units=n,question=q.group(),start=q.start(),end=nxt.start()))

# Deterministic lexical TF-IDF control vectors: this is NOT BGE-M3 and NOT a semantic benchmark.
STOP=set('a an the of in on to for and or is are was were be been with as at by from it this that what how when where do does can i my your our you we will may should after before which have has not no all'.split())
def words(s): return [w for w in re.findall(r'[a-z]+|\d+(?:[,.]\d+)*',s.lower()) if len(w)>1 and w not in STOP]
base=CHUNKS['fixed_500_80']; texts=[rows[c['doc']]['title']+'\n'+c['text'] for c in base]
df=Counter(w for t in texts for w in set(words(t)))
vocab=[w for w,f in sorted(df.items(),key=lambda z:(-z[1],z[0])) if 2<=f<len(base)*.8][:1024]
vid={w:i for i,w in enumerate(vocab)}
idf=np.array([np.log((1+len(base))/(1+df[w]))+1 for w in vocab],dtype='float32')
def encode(text):
    v=np.zeros(1024,dtype='float32')
    for w,n in Counter(words(text)).items():
        if w in vid: v[vid[w]]=(1+np.log(n))*idf[vid[w]]
    norm=np.linalg.norm(v)
    if norm:v/=norm
    return v
X=np.stack([encode(t) for t in texts]).astype('float32')
Q=np.stack([encode(p['query']) for p in GOLD]).astype('float32')
faiss.normalize_L2(X); faiss.normalize_L2(Q)
flat=faiss.IndexFlatIP(1024)
t=time.perf_counter(); flat.add(X); flat_build=(time.perf_counter()-t)*1000
hnsw=faiss.IndexHNSWFlat(1024,16,faiss.METRIC_INNER_PRODUCT)
hnsw.hnsw.efConstruction=80; hnsw.hnsw.efSearch=32
t=time.perf_counter(); hnsw.add(X); hnsw_build=(time.perf_counter()-t)*1000
s,I=flat.search(Q,5); sh,Ih=hnsw.search(Q,5)
mat=Q@X.T
reference=np.sort(mat,axis=1)[:,-5:][:,::-1]
maxerror=float(np.max(np.abs(s-reference)))
assert maxerror<1e-5
unicode_probe={}
try:
    faiss.write_index(flat,str(OUT/'unicode_path_probe.faiss'))
    unicode_probe['native_write_ok']=True
except RuntimeError as exc:
    unicode_probe={'native_write_ok':False,'error':str(exc)}
(OUT/'lexical_control_flat.faiss').write_bytes(faiss.serialize_index(flat).tobytes())
(OUT/'lexical_control_hnsw.faiss').write_bytes(faiss.serialize_index(hnsw).tobytes())
(OUT/'lexical_control_mapping.json').write_text(json.dumps([{k:c[k] for k in ['id','doc','ord','start','end']} for c in base],indent=2),encoding='utf-8')
reload=faiss.deserialize_index(np.frombuffer((OUT/'lexical_control_flat.faiss').read_bytes(),dtype=np.uint8)); sr,Ir=reload.search(Q,5)
assert np.array_equal(I,Ir) and np.allclose(s,sr)
# Single-query latency, 100 timed runs after 10 warmups, one thread, precomputed query vectors only.
def bench(index):
    for j in range(10): index.search(Q[j%len(Q):j%len(Q)+1],5)
    out=[]
    for j in range(100):
        q=Q[j%len(Q):j%len(Q)+1]; t=time.perf_counter_ns(); index.search(q,5); out.append((time.perf_counter_ns()-t)/1e6)
    return {'median_ms':round(float(np.median(out)),4),'p95_ms':round(float(np.percentile(out,95)),4),'runs':100}
index_stats=dict(kind='1024-d TF-IDF lexical control, not BGE-M3',faiss_version=faiss.__version__,numpy_version=np.__version__,dimensions=1024,actual_vocabulary=len(vocab),n=len(X),threads=1,flat_build_ms=round(flat_build,3),hnsw_build_ms=round(hnsw_build,3),flat_index_bytes=(OUT/'lexical_control_flat.faiss').stat().st_size,hnsw_index_bytes=(OUT/'lexical_control_hnsw.faiss').stat().st_size,flat_latency=bench(flat),hnsw_latency=bench(hnsw),hnsw_recall_at5_ids=round(sum(len(set(a)&set(b))/5 for a,b in zip(I,Ih))/len(Q),4),flat_numpy_score_max_error=maxerror,reload_exact=True,excluded='No tokenization, query encoding, model loading, DB access or application overhead included in index timings; lexical queries chosen from corpus, no held-out semantic conclusions.')
lexical=[]
for p,scores,ids in zip(GOLD,s,I):
    hits=[]
    for score,idx in zip(scores,ids):
        c=base[int(idx)]; hits.append(dict(chunk_id=c['id'],doc=c['doc'],score=float(score),url=rows[c['doc']]['url'],contains_full_probe=c['doc']==p['doc'] and c['start']<=p['start'] and c['end']>=p['end']))
    lexical.append(dict(probe=p['id'],query=p['query'],source_doc_top5=any(h['doc']==p['doc'] for h in hits),full_probe_top5=any(h['contains_full_probe'] for h in hits),hits=hits))
# Three query-interface controls: English labels, wrong source column, and filter-after-top5 loss.
alias={col:sorted(set(r['topic'] for r in rows if r['column']==col)) for col in sorted(set(r['column'] for r in rows))}
visa=dict(source_url=rows[21]['url'],actual_column=rows[21]['column'],actual_topic=rows[21]['topic'],geo_only_contains_source=rows[21]['column']=='visa_geo',english_fees_as_topic_candidates=sum(r['topic']=='fees' for r in rows),fees_as_column_candidates=sum(r['column']=='fees' for r in rows),column_to_topic=alias)
# Handcrafted normalized vector fixture proves policy without dependence on corpus or any model.
scores=np.array([.99,.98,.97,.96,.95,.94,.93,.92,.91,.90],dtype='float32')
fixture=np.zeros((10,1024),dtype='float32'); fixture[:,0]=scores; fixture[:,1]=np.sqrt(1-scores*scores)
fidx=faiss.IndexFlatIP(1024); fidx.add(fixture); fq=np.zeros((1,1024),dtype='float32'); fq[0,0]=1
_,fi=fidx.search(fq,5); allowed=np.arange(5,10); after=[int(i) for i in fi[0] if i in allowed]
subset=faiss.IndexFlatIP(1024);subset.add(fixture[allowed]); _,pref=subset.search(fq,5); before=[int(allowed[i]) for i in pref[0]]
assert len(after)==0 and len(before)==5
filter_fixture=dict(kind='synthetic correctness fixture, not model-quality evidence',post_filter_ids=after,pre_filter_ids=before)

# Database lifecycle test uses project Python in a separate small script (no production writes).
conn=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True)
db_state=dict(active=conn.execute('SELECT COUNT(*) FROM documents WHERE active=1').fetchone()[0],dirty=conn.execute('SELECT COUNT(*) FROM documents WHERE active=1 AND index_dirty=1').fetchone()[0],chunks=conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0],versions=[x[0] for x in conn.execute('SELECT DISTINCT corpus_sha256 FROM documents WHERE active=1')]); conn.close()
RESULT={'date':'2026-10-17','source':{'corpus_sha256':sha(CORPUS),'documents':len(rows),'database':db_state,'columns':dict(Counter(r['column'] for r in rows)),'total_proxy_units':sum(count(r['content']) for r in rows),'tokenization':'regex English words/numbers/punctuation proxy, NOT BGE-M3 tokens; official tokenizer download failed','model_status':'No local BGE-M3 weights or torch/sentence-transformers runtime; no BGE inference performed','hardware':platform.processor(),'python':platform.python_version()},'chunking':stats,'span_coverage':spans,'navigation_audit':nav_audit,'faq_audit':{'heuristic_question_to_next_question_spans':len(faq_spans),'over_500_proxy_units':sum(s['proxy_units']>500 for s in faq_spans),'largest':sorted(faq_spans,key=lambda s:-s['proxy_units'])[:5]},'index_control':index_stats,'lexical_probe_results':lexical,'metadata_interface':visa,'filter_fixture':filter_fixture,'windows_unicode_path':unicode_probe,'source_hashes_before':BEFORE}
RESULT['source_hashes_after']={str(p.relative_to(ROOT)):sha(p) for p in SOURCE_FILES}
assert RESULT['source_hashes_after']==BEFORE
(OUT/'实验结果.json').write_text(json.dumps(RESULT,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'切块样例.json').write_text(json.dumps({name:[dict(c,source_url=rows[c['doc']]['url']) for c in cc if c['doc'] in (21,32,42,107,127,30)] for name,cc in CHUNKS.items()},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'chunking':stats,'navigation_audit':nav_audit,'index_control':index_stats,'lexical_source_doc_top5':sum(p['source_doc_top5'] for p in lexical),'lexical_full_probe_top5':sum(p['full_probe_top5'] for p in lexical),'probes':len(GOLD),'source_read_only':True},ensure_ascii=False,indent=2))
