"""Xiaoxing memory: additive SQLite migration, provenance, hybrid recall and audit."""
from memory_core import MemoryStore as LegacyStore, now_iso, parse_time
from memory_models import Models, ModelUnavailable
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from affect_core import AffectStore
from memory_retention import Retention
from memory_diary import DailyImpressions
from memory_vector_index import QdrantVectorIndex,VectorIndexUnavailable
from memory_continuity import ContinuityStore
AFFECT_POOL=ThreadPoolExecutor(max_workers=4,thread_name_prefix="affect")
import collections, hashlib, json, math, re, sqlite3, time, uuid

STOP=set('什么 怎么 为什么 这个 那个 一个 我们 你们 他们 现在 今天 事情 可以 知道 觉得 记得 记住 好的 继续 谢谢'.split())
ACK=re.compile(r'^(?:好|好的|嗯|嗯嗯|行|收到|谢谢|继续|重启|可以|知道了)[。！!，,\s…]*$')
SECRET=re.compile(r'(?i)(?:sk-[a-z0-9_-]{18,}|Bearer\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:password|api_key|access_token|refresh_token)\s*[=:]\s*\S+)')
LAYERS={'core','semantic','episodic','procedural','experience'}
GRAPH_RELATION_WEIGHT={
    'same_event':1.0,'updates':1.0,'contradicts':.98,'caused_by':.96,
    'resulted_in':.96,'motivated':.94,'depends_on':.94,'supports':.92,
    'before':.9,'after':.9,'related':.72,
}
GRAPH_MIN_CONFIDENCE=.85
GRAPH_BRANCH_LIMIT=4
GRAPH_CANDIDATE_LIMIT=16

def terms(text):
    s=str(text or '').lower();out=re.findall(r'[a-z0-9_\-]{2,}',s)
    for run in re.findall(r'[\u3400-\u9fff]+',s):
        out += [run[i:i+2] for i in range(len(run)-1)]
    return [x for x in out if x not in STOP]

def tokens(value):return math.ceil(len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())/3)+8

def clean(value,n=4000):return re.sub(r'\s+',' ',str(value or '')).strip()[:n]

def digest(value):return hashlib.sha256(str(value).encode()).hexdigest()

SCHEMA='''
CREATE TABLE IF NOT EXISTS memory_meta(memory_id TEXT PRIMARY KEY REFERENCES memories(id),layer TEXT NOT NULL DEFAULT 'episodic',review_status TEXT NOT NULL DEFAULT 'legacy',entities_json TEXT NOT NULL DEFAULT '[]',updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memory_evidence(memory_id TEXT NOT NULL REFERENCES memories(id),event_id TEXT NOT NULL REFERENCES raw_events(id),quote TEXT NOT NULL,PRIMARY KEY(memory_id,event_id,quote));
CREATE TABLE IF NOT EXISTS memory_links(from_id TEXT NOT NULL REFERENCES memories(id),to_id TEXT NOT NULL REFERENCES memories(id),relation TEXT NOT NULL,confidence REAL NOT NULL,source TEXT NOT NULL,PRIMARY KEY(from_id,to_id,relation));
CREATE INDEX IF NOT EXISTS memory_links_to ON memory_links(to_id,relation,confidence DESC);
CREATE INDEX IF NOT EXISTS memory_links_relation ON memory_links(relation,confidence DESC);
CREATE TABLE IF NOT EXISTS memory_vectors(memory_id TEXT PRIMARY KEY REFERENCES memories(id),model TEXT NOT NULL,content_hash TEXT NOT NULL,vector_json TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recall_log(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,namespace TEXT NOT NULL,session_key TEXT,query TEXT,mode TEXT,reason TEXT,candidates_json TEXT,selected_json TEXT,tokens INTEGER,latency_ms INTEGER,model_usage_json TEXT);
CREATE INDEX IF NOT EXISTS recall_recent ON recall_log(created_at DESC);
CREATE TABLE IF NOT EXISTS memory_jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL DEFAULT 0,lease_until REAL NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,result_json TEXT,error TEXT);
CREATE TABLE IF NOT EXISTS memory_seen(session_key TEXT NOT NULL,memory_id TEXT NOT NULL,version TEXT NOT NULL,seen_at REAL NOT NULL,hits INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(session_key,memory_id));
CREATE TABLE IF NOT EXISTS memory_state(key TEXT PRIMARY KEY,value_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memory_projection_state(backend TEXT NOT NULL,memory_id TEXT NOT NULL,content_hash TEXT NOT NULL,status TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(backend,memory_id));
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(memory_id UNINDEXED,body,tokenize='unicode61');
CREATE TABLE IF NOT EXISTS event_sources(event_id TEXT PRIMARY KEY REFERENCES raw_events(id),source TEXT,source_msg_id TEXT);
CREATE TABLE IF NOT EXISTS memory_documents(id TEXT PRIMARY KEY,title TEXT NOT NULL,source_ref TEXT NOT NULL,body TEXT NOT NULL,sha256 TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memory_document_evidence(memory_id TEXT NOT NULL REFERENCES memories(id),document_id TEXT NOT NULL REFERENCES memory_documents(id),quote TEXT NOT NULL,PRIMARY KEY(memory_id,document_id,quote));
'''

class MemoryStore(LegacyStore):
    def __init__(self,db_path,archive_dir,models=None):
        super().__init__(db_path,archive_dir);self.models=models or Models();self.vector_index=QdrantVectorIndex()
        with self.connect() as db:
            db.executescript(SCHEMA)
            # additive migration: memory_seen.hits enables cooldown de-weighting on existing DBs.
            try:
                if 'hits' not in [c[1] for c in db.execute("PRAGMA table_info(memory_seen)").fetchall()]:
                    db.execute("ALTER TABLE memory_seen ADD COLUMN hits INTEGER NOT NULL DEFAULT 0")
            except Exception:pass
            # Initial index has no extraction or changes to legacy content/status.
            for r in db.execute('SELECT id,kind,pinned,content,summary,tags_json FROM memories').fetchall():
                db.execute('INSERT OR IGNORE INTO memory_meta VALUES(?,?,?,?,?)',(r['id'],'core' if r['pinned'] else ('experience' if r['kind'] in ('feel','diary','dream') else 'episodic'),'legacy','[]',now_iso()))
                if not db.execute('SELECT 1 FROM memory_fts WHERE memory_id=?',(r['id'],)).fetchone():self._index(db,r['id'])

        self.affect=AffectStore(self);self.retention=Retention(self);self.daily=DailyImpressions(self);self.continuity=ContinuityStore(self)

    def _effective_strength(self,row,at=None):
        state=self.retention.state(row["id"],at.timestamp() if at else None)
        return state["weight"] if state else float(row.get("strength",3))

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.db_path,timeout=15);db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db: yield db
        finally: db.close()

    def _index(self,db,mid):
        r=db.execute('SELECT * FROM memories WHERE id=?',(mid,)).fetchone()
        if not r:return
        db.execute('DELETE FROM memory_fts WHERE memory_id=?',(mid,))
        db.execute('INSERT INTO memory_fts(memory_id,body) VALUES(?,?)',(mid,' '.join(terms(r['content']+' '+r['summary']+' '+r['tags_json']))))

    def enqueue(self,kind,payload,key=None):
        jid=key or 'job_'+uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO memory_jobs(id,kind,payload_json,created_at,updated_at) VALUES(?,?,?,?,?)',(jid,kind,json.dumps(payload,ensure_ascii=False),now_iso(),now_iso()))
        return jid

    def upsert(self,data):
        if SECRET.search(str(data.get('content',data.get('text','')))):raise ValueError('credential_like_content_rejected')
        data=dict(data);data['content']=clean(data.get('content',data.get('text')),12000)
        layer=data.get('layer','episodic')
        if layer not in LAYERS:raise ValueError('invalid_layer')
        result=super().upsert(data);m=result['memory'];mid=m['id']
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO memory_meta VALUES(?,?,?,?,?)',(mid,layer,data.get('review_status','self_written'),'[]',now_iso()))
            self._index(db,mid)
        self.retention.seed()
        self.enqueue('enrich',{'id':mid},'enrich:'+mid+':'+m['content_hash'])
        return {'status':result['status'],'id':mid,'version_status':m['version_status'],'memory':m}

    def ingest_event(self,data):
        content=str(data.get('content') or '').strip()
        if not content:raise ValueError('content_required')
        ns=str(data.get('namespace') or 'default');role=str(data.get('role') or 'user');session=data.get('session_id');occurred=data.get('occurred_at') or now_iso();source_id=data.get('source_msg_id')
        # A repeated sentence in two real turns is two experiences, but retries of
        # the same source message remain exactly once per role.
        key=digest(ns+'\0'+str(source_id or session)+'\0'+role+'\0'+(str(source_id) if source_id else content))
        eid='evt_'+uuid.uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT id FROM raw_events WHERE content_hash=?',(key,)).fetchone()
            if old:return {'id':old['id'],'stored':True,'duplicate':True}
            seq=db.execute('SELECT COALESCE(MAX(sequence_no),-1)+1 FROM raw_events WHERE namespace=? AND session_id IS ?',(ns,session)).fetchone()[0]
            db.execute('INSERT INTO raw_events VALUES(?,?,?,?,?,?,?,?,?,?)',(eid,ns,session,seq,role,content,occurred,now_iso(),key,now_iso()))
            db.execute('INSERT OR REPLACE INTO event_sources VALUES(?,?,?)',(eid,data.get('source','conversation'),source_id))
            if data.get('source') not in ('wake','task_completion','reminder') and not SECRET.search(content):
                context_ids=[x[0] for x in db.execute('SELECT id FROM raw_events WHERE namespace=? AND session_id IS ? ORDER BY sequence_no DESC LIMIT 4',(ns,session))]
                db.execute('INSERT OR IGNORE INTO memory_jobs(id,kind,payload_json,created_at,updated_at) VALUES(?,?,?,?,?)',('live-event:'+eid,'live_extract',json.dumps({'ids':list(reversed(context_ids)),'focus_ids':[eid]}),now_iso(),now_iso()))
                if role=='user':
                    db.execute('INSERT OR IGNORE INTO memory_jobs(id,kind,payload_json,created_at,updated_at) VALUES(?,?,?,?,?)',('affect-event:'+eid,'affect_event',json.dumps({'id':eid}),now_iso(),now_iso()))
        self.append_archive({'type':'raw_event','event':{'id':eid,'role':role,'content':content,'occurred_at':occurred,'session_id':session}})
        return {'id':eid,'stored':True}

    def get(self,mid):
        m=super().get(mid)
        if not m:return None
        with self.connect() as db:
            meta=db.execute('SELECT * FROM memory_meta WHERE memory_id=?',(mid,)).fetchone()
            if meta:m.update(dict(meta));m['entities']=json.loads(m.pop('entities_json','[]'))
            m['evidence']=[dict(x) for x in db.execute('SELECT e.event_id,e.quote,r.role,r.occurred_at FROM memory_evidence e JOIN raw_events r ON r.id=e.event_id WHERE e.memory_id=?',(mid,))]
            m['links']=[dict(x) for x in db.execute("SELECT from_id,to_id,relation,confidence,source FROM memory_links WHERE from_id=? OR to_id=? ORDER BY CASE WHEN relation='shared_entity' THEN 1 ELSE 0 END,confidence DESC LIMIT 40",(mid,mid))]
            m['document_evidence']=[dict(x) for x in db.execute('SELECT d.title,d.source_ref,d.sha256,e.quote FROM memory_document_evidence e JOIN memory_documents d ON d.id=e.document_id WHERE e.memory_id=?',(mid,))]
            m['conflicts']=[dict(x) for x in db.execute("SELECT id,content,occurred_at FROM memories WHERE namespace=? AND fact_key=? AND id!=? AND version_status='current'",(m['namespace'],m.get('fact_key'),mid))] if m.get('version_status')=='candidate' else []
        m['retention']=self.retention.state(mid)
        m['effective_strength']=round(self._effective_strength(m),3)
        return m

    def browse(self,args):
        ns=str(args.get('namespace') or 'default');limit=max(1,min(100,int(args.get('limit',30))));offset=max(0,int(args.get('offset',0)))
        where=['m.namespace=?'];vals=[ns]
        if args.get('status','current')!='all':where.append('m.version_status=?');vals.append(args.get('status','current'))
        if args.get('layer') in LAYERS:where.append('x.layer=?');vals.append(args['layer'])
        if args.get('query'):
            where.append('(m.content LIKE ? OR m.summary LIKE ? OR m.tags_json LIKE ? OR m.fact_key LIKE ?)');vals += ['%'+str(args['query'])[:200]+'%']*4
        clause=' AND '.join(where)
        with self.connect() as db:
            total=db.execute('SELECT count(*) FROM memories m LEFT JOIN memory_meta x ON x.memory_id=m.id WHERE '+clause,vals).fetchone()[0]
            rows=db.execute('SELECT m.*,x.layer,x.review_status,x.entities_json FROM memories m LEFT JOIN memory_meta x ON x.memory_id=m.id WHERE '+clause+' ORDER BY m.pinned DESC,m.occurred_at DESC LIMIT ? OFFSET ?',vals+[limit,offset]).fetchall()
        items=[]
        for r in rows:
            m=self._row(r);m['entities']=json.loads(m.pop('entities_json','[]') or '[]');m['effective_strength']=round(self._effective_strength(m),3);m['retention']=self.retention.state(m['id']);items.append(m)
        return {'items':items,'total':total,'offset':offset,'next_offset':offset+limit if offset+limit<total else None}

    def evidence(self,event_id,namespace='default'):
        with self.connect() as db:
            r=db.execute('SELECT * FROM raw_events WHERE id=? AND namespace=?',(event_id,namespace)).fetchone()
            if not r:return {'items':[]}
            rows=db.execute('SELECT id,role,content,occurred_at,sequence_no FROM raw_events WHERE namespace=? AND session_id IS ? AND sequence_no BETWEEN ? AND ? ORDER BY sequence_no LIMIT 5',(namespace,r['session_id'],r['sequence_no']-2,r['sequence_no']+2)).fetchall()
        return {'items':[dict(x) for x in rows]}

    def sync_capsule(self,data):
        # Both old string capsules and evidence-bearing objects are queued for verification.
        # Nothing is automatically promoted from a summary alone.
        cap=data.get('capsule') or {};items=[]
        for field in ('about_her','relationship','watchouts'):
            for x in cap.get(field,[])[:8]:
                text=x.get('text') if isinstance(x,dict) else x
                if isinstance(text,str) and text.strip():items.append({'section':field,'text':clean(text,1000)})
        if not items:return {'queued':0,'written':0}
        payload={'items':items,'namespace':data.get('namespace','default'),'session_id':data.get('session_id'),'window_id':data.get('window_id')}
        jid=self.enqueue('capsule',payload,'capsule:'+digest(json.dumps(payload,sort_keys=True,ensure_ascii=False)))
        return {'queued':len(items),'written':0,'job_id':jid}

    @staticmethod
    def _review_text(memory):
        text=memory.get('summary') or memory['content']
        path=memory.get('path') or []
        if len(path)>1:
            chain=[]
            for step in path:
                chain.append(step.get('text',''))
                if step.get('relation_to_next'):chain.append('['+step['relation_to_next']+']')
            text += '\n关系路径：'+' -> '.join(chain)
        return text

    @staticmethod
    def _fallback_review_pool(pool,limit=8):
        def _rel(m):
            try:s=float(m.get('semantic_score') or 0.0)
            except (TypeError,ValueError):s=0.0
            return (1 if m.get('lexical_hit') else 0,s)
        pool=sorted(pool,key=_rel,reverse=True)
        direct=[m for m in pool if 'graph' not in m.get('retrieval_channels',[])]
        graph=[m for m in pool if 'graph' in m.get('retrieval_channels',[])]
        chosen=direct[:5]+graph[:3];seen={m['id'] for m in chosen}
        chosen += [m for m in pool if m['id'] not in seen][:max(0,limit-len(chosen))]
        return chosen[:limit]

    def _graph_expand(self,seeds,db,ns,include_history=False,max_depth=3):
        """Bounded best-path traversal over reviewed semantic edges.

        The graph is a derived retrieval index. It may propose a path, but the
        final relevance judge still has to validate every step before anything
        reaches the primary model.
        """
        max_depth=max(0,min(3,int(max_depth)))
        if not seeds or not max_depth:return []
        seed_rank={m['id']:1/(i+1) for i,m in enumerate(seeds[:8])}
        row_cache={m['id']:m for m in seeds[:8]}
        states={mid:{'ids':[mid],'edges':[],'score':score} for mid,score in seed_rank.items()}
        frontier=dict(states)
        for depth in range(1,max_depth+1):
            node_ids=list(frontier)
            if not node_ids:break
            marks=','.join('?' for _ in node_ids)
            rel_marks=','.join('?' for _ in GRAPH_RELATION_WEIGHT)
            sql=("SELECT from_id,to_id,relation,confidence,source FROM memory_links "
                 "WHERE confidence>=? AND relation IN ("+rel_marks+") AND "
                 "(from_id IN ("+marks+") OR to_id IN ("+marks+"))")
            rows=db.execute(sql,[GRAPH_MIN_CONFIDENCE,*GRAPH_RELATION_WEIGHT,*node_ids,*node_ids]).fetchall()
            adjacent=collections.defaultdict(list)
            for edge in rows:
                e=dict(edge);a=e['from_id'];b=e['to_id']
                adjacent[a].append((b,e,'forward'))
                adjacent[b].append((a,e,'reverse'))
            neighbor_ids=list({neighbor for current in node_ids for neighbor,_,_ in adjacent.get(current,[]) if neighbor not in row_cache})
            if neighbor_ids:
                node_marks=','.join('?' for _ in neighbor_ids)
                status='' if include_history else " AND m.version_status='current'"
                query=("SELECT m.*,x.layer FROM memories m LEFT JOIN memory_meta x ON x.memory_id=m.id "
                       "WHERE m.namespace=? AND m.id IN ("+node_marks+")"+status)
                for row in db.execute(query,[ns,*neighbor_ids]).fetchall():row_cache[row['id']]=self._row(row)
            next_frontier={}
            for current,state in frontier.items():
                options=sorted(adjacent.get(current,[]),key=lambda x:GRAPH_RELATION_WEIGHT[x[1]['relation']]*x[1]['confidence'],reverse=True)
                used=0
                for neighbor,edge,direction in options:
                    if neighbor not in row_cache or neighbor in state['ids']:continue
                    # "related" is useful for discovery but is too vague to
                    # compose into a multi-hop factual claim.
                    if edge['relation']=='related' and (depth>1 or any(x['relation']=='related' for x in state['edges'])):continue
                    used+=1
                    if used>GRAPH_BRANCH_LIMIT:break
                    score=state['score']*edge['confidence']*GRAPH_RELATION_WEIGHT[edge['relation']]*(.88**depth)
                    candidate={'ids':state['ids']+[neighbor],'edges':state['edges']+[{**edge,'direction':direction}],'score':score}
                    old=states.get(neighbor)
                    if old is None or score>old['score']:
                        states[neighbor]=candidate;next_frontier[neighbor]=candidate
            frontier=next_frontier
        found=[]
        for endpoint,state in states.items():
            if len(state['ids'])<2:continue
            steps=[]
            for i,mid in enumerate(state['ids']):
                row=row_cache[mid];step={'id':mid,'text':clean(row.get('summary') or row['content'],360),'at':row['occurred_at'][:10],'status':row['version_status']}
                if row.get('emotion_label'):step['emotion']={'label':row['emotion_label'],'intensity':row['emotion_intensity']}
                if i<len(state['edges']):
                    edge=state['edges'][i];step.update(relation_to_next=edge['relation'],confidence=round(edge['confidence'],3),direction=edge['direction'])
                steps.append(step)
            found.append({'id':endpoint,'path':steps,'graph_depth':len(steps)-1,'path_score':round(state['score'],6)})
        return sorted(found,key=lambda x:(x['path_score'],-x['graph_depth']),reverse=True)[:GRAPH_CANDIDATE_LIMIT]

    def _candidates(self,query,ns,include_history=False,graph_depth=3):
        self.retention.sweep()
        qs=list(dict.fromkeys(terms(query)))[:48];lex={};vec={};external={};degraded=[]
        with self.connect() as db:
            if qs:
                match=' OR '.join('"'+q.replace('"','')+'"' for q in qs)
                status='' if include_history else " AND m.version_status='current'"
                hits=db.execute('SELECT f.memory_id,bm25(memory_fts) rank FROM memory_fts f JOIN memories m ON m.id=f.memory_id WHERE memory_fts MATCH ? AND m.namespace=?'+status+' ORDER BY rank LIMIT 40',(match,ns)).fetchall()
                lex={r['memory_id']:1/(i+1) for i,r in enumerate(hits)}
        try:
            qv=self.models.query_vector(query);qn=math.sqrt(sum(x*x for x in qv)) or 1
            used_external=False
            if self.vector_index.enabled:
                try:
                    external=self.vector_index.search(qv,ns,self.models.embed_model,40,.35);used_external=True
                except VectorIndexUnavailable as e:degraded.append('vector_index:'+str(e))
            with self.connect() as db:
                status='' if include_history else " AND m.version_status='current'"
                delta=(" LEFT JOIN memory_projection_state p ON p.backend='qdrant' AND p.memory_id=m.id "
                       "WHERE m.namespace=? AND v.model=? AND v.content_hash=m.content_hash AND "
                       "(p.memory_id IS NULL OR p.content_hash!=m.content_hash OR p.status!=m.version_status)") if used_external else " WHERE m.namespace=? AND v.model=? AND v.content_hash=m.content_hash"
                vector_rows=db.execute("SELECT m.id,v.vector_json FROM memories m JOIN memory_vectors v ON v.memory_id=m.id"+delta+status,(ns,self.models.embed_model)).fetchall()
            if vector_rows:
                for r in vector_rows:
                    v=json.loads(r['vector_json'])
                    if len(v)==len(qv):vec[r['id']]=sum(a*b for a,b in zip(v,qv))/(qn*(math.sqrt(sum(x*x for x in v)) or 1))
        except Exception as e:degraded.append('embedding:'+type(e).__name__)
        candidate_ids=set(lex)|set(vec)|set(external)
        if not candidate_ids:return [],degraded
        marks=','.join('?' for _ in candidate_ids)
        status='' if include_history else " AND m.version_status='current'"
        with self.connect() as db:
            rows=db.execute("SELECT m.*,x.layer FROM memories m LEFT JOIN memory_meta x ON x.memory_id=m.id WHERE m.namespace=? AND m.id IN ("+marks+")"+status,[ns,*candidate_ids]).fetchall()
        row_by_id={r['id']:r for r in rows}
        for mid,item in external.items():
            row=row_by_id.get(mid)
            if row is not None and item['content_hash']==row['content_hash']:vec[mid]=item['score']
        vr={k:1/(i+1) for i,(k,v) in enumerate(sorted(vec.items(),key=lambda x:x[1],reverse=True)[:40]) if v>=0.35}
        pool=[]
        for r in rows:
            mid=r['id']
            if mid not in lex and mid not in vr:continue
            m=self._row(r)
            # Reciprocal rank fusion: prior importance alone cannot create relevance.
            score=(1/(60+1/lex[mid]) if mid in lex else 0)+(1/(60+1/vr[mid]) if mid in vr else 0)
            score*=.5+.5*self._effective_strength(m)/5
            m['score']=round(score,6);m['semantic_score']=round(vec.get(mid,0),4);m['lexical_hit']=mid in lex
            m['retrieval_channels']=[x for x,ok in [('lexical',mid in lex),('vector',mid in vr)] if ok];pool.append(m)
        pool.sort(key=lambda x:x['score'],reverse=True)
        direct=pool[:16];known={x['id']:x for x in direct}
        with self.connect() as db:
            graph=self._graph_expand(pool[:8],db,ns,include_history,graph_depth)
        for item in graph:
            mid=item['id']
            if mid in known:
                known[mid].update(item);known[mid]['retrieval_channels']=list(dict.fromkeys(known[mid]['retrieval_channels']+['graph']))
                continue
            with self.connect() as db:
                row=db.execute('SELECT m.*,x.layer FROM memories m LEFT JOIN memory_meta x ON x.memory_id=m.id WHERE m.id=? AND m.namespace=?',(mid,ns)).fetchone()
            if not row:continue
            m=self._row(row)
            m.update(score=0,semantic_score=0,lexical_hit=False,retrieval_channels=['graph'],**item);known[mid]=m
        graph_only=sorted((m for m in known.values() if m['id'] not in {x['id'] for x in direct}),key=lambda x:x.get('path_score',0),reverse=True)
        return (direct+graph_only)[:32],degraded

    @staticmethod
    def brief(m):
        out={'id':m['id'],'text':m.get('summary') or m['content'],'at':m['occurred_at'][:10],'status':m['version_status'],'source':m.get('source',''),'layer':m.get('layer','episodic')}
        if m.get('emotion_label'):out['emotion']={'label':m['emotion_label'],'intensity':m['emotion_intensity']}
        if m.get('retrieval_channels'):out['retrieval_channels']=m['retrieval_channels']
        if m.get('path'):
            out.update(path=m['path'],graph_depth=m['graph_depth'],path_score=m['path_score'])
        return out

    @staticmethod
    def _render(m,tier='full'):
        """Three confidence-weighted injection tiers. Shape stays bridge-compatible;
        extra keys (tier/channel) are ignored by the client's memory formatter.
        full=whole brief (+relation path); summary=trimmed text +short path; light=one-liner."""
        b=MemoryStore.brief(m)
        if tier=='full':return b
        if tier=='summary':
            b['text']=clean(b.get('text'),360)
            if b.get('path'):b['path']=b['path'][:2]
            b['tier']='summary';return b
        light={'id':b['id'],'text':clean(b.get('text'),120),'at':b.get('at'),'status':b.get('status'),'tier':'light'}
        if b.get('source'):light['source']=b['source']
        return light

    def recall_pack(self,args):
        start=time.monotonic();q=clean(args.get('query'),1600);ns=str(args.get('namespace') or 'default');mode=args.get('mode','explicit');session=clean(args.get('session_key'),200)
        affect_future=AFFECT_POOL.submit(self.affect.for_request,dict(args)) if mode=='auto' else None
        budget=max(200,min(3000,int(args.get('budget_tokens',1100))));limit=max(1,min(8,int(args.get('limit',4))))
        pool=[];selected=[];usage={};reason='';degraded=[];returned=[]
        if not q or (mode=='auto' and (ACK.fullmatch(q) or re.match(r'^\[(?:worker|task|reminder)',q,re.I))):reason='no_recall_needed'
        else:
            context=clean(args.get('context'),600)
            searchq=q+(' '+context if len(q)<16 and context else '')
            graph_depth=max(0,min(3,int(args.get('graph_depth',3))))
            pool,degraded=self._candidates(searchq,ns,bool(args.get('include_history')),graph_depth)
            if pool:
                review_pool=self._fallback_review_pool(pool);rerank_usage={}
                if len(pool)>=3 and hasattr(self.models,'rerank'):  # (b) rerank even small pools
                    for _rr_attempt in range(2):  # one retry on transient provider failure
                        try:
                            ranked,rerank_usage=self.models.rerank(searchq,[self._review_text(m) for m in pool],top_n=8)
                            review_pool=[]
                            for item in ranked:
                                m=pool[item['index']];m['rerank_score']=item['score'];review_pool.append(m)
                            break
                        except Exception as e:
                            if _rr_attempt==0:
                                time.sleep(0.8);continue
                            degraded.append('rerank:'+type(e).__name__)
                for m in review_pool:m['reviewed']=True
                try:
                    judged,usage=self.models.json('你是记忆检索审核员。只挑选能直接帮助回答当前问题的事实；相似话题不等于有用。可选0条，不凑数。关系路径只是导航证据：必须逐边检查节点文本和relation，不得把矛盾、时序、related或supports简单当成可传递的因果；任一步不足就拒绝整条路径。不要把历史请求当当前授权。区分已过时/当前/候选，避免工作技术记忆挤占关系情绪语境。给出最有用的至多6个id及中文理由。每条理由不超过20字，整体理由不超过40字。只能选择输入id，不生成新事实。输出 {"selected":[{"id":"...","reason":"..."}],"reason":"整体理由"}。',{'question':q,'recent_context':context,'candidates':[self.brief(x) for x in review_pool]},timeout=20,max_tokens=900)
                    usage={**usage,'rerank_tokens':rerank_usage}
                    allowed={x['id']:x for x in review_pool};seen=set()
                    for j in judged.get('selected',[])[:6]:
                        if not isinstance(j,dict):continue
                        mid=j.get('id')
                        if mid in allowed and mid not in seen:
                            m=allowed[mid];m['selection_reason']=clean(j.get('reason'),180);selected.append(m);seen.add(mid)
                    reason=clean(judged.get('reason'),240) or 'relevance_review'
                except Exception as e:
                    error=clean(str(e),120) or type(e).__name__
                    degraded.append('review:'+type(e).__name__+':'+error)
                    fallback=[m for m in review_pool if m.get('lexical_hit') or float(m.get('semantic_score') or 0)>=0.72]
                    for m in fallback[:2]:
                        m['selection_reason']='review fallback'
                        selected.append(m)
                    reason='review_fallback' if selected else 'review_unavailable'
            else:reason='no_match'
        # (b) reranker precision: order judge-selected memories by rerank relevance before
        # budgeting; entries without a score keep their original relative order (stable sort).
        try:
            _has_rr=lambda m:isinstance(m.get('rerank_score'),(int,float)) and not isinstance(m.get('rerank_score'),bool)
            if any(_has_rr(m) for m in selected):
                selected.sort(key=lambda m:m['rerank_score'] if _has_rr(m) else -1.0,reverse=True)
        except Exception as e:
            degraded.append('rerank_sort:'+type(e).__name__)
        used=0;omitted=[]
        # (a) cooldown de-weighting: precompute per-memory injection history for this session.
        # Falls back to the legacy 30-minute hard skip if this new path fails.
        cool={};cool_ok=False
        try:
            if session and mode=='auto' and selected:
                ids=[m['id'] for m in selected];marks=','.join('?' for _ in ids)
                with self.connect() as cdb:
                    for row in cdb.execute('SELECT memory_id,version,seen_at,hits FROM memory_seen WHERE session_key=? AND memory_id IN ('+marks+')',[session,*ids]).fetchall():
                        cool[row['memory_id']]=dict(row)
            cool_ok=True
        except Exception as e:
            degraded.append('cooldown:'+type(e).__name__);cool={};cool_ok=False
        def _cool_info(m):
            v=digest(m['content_hash']+str(m.get('summary'))+m['version_status'])
            protected=bool(m.get('pinned')) or m.get('layer')=='core'
            info=cool.get(m['id'])
            if not info or info.get('version')!=v:return {'recent':False,'hits':0,'protected':protected}
            return {'recent':(time.time()-info['seen_at'])<1800,'hits':int(info.get('hits') or 0),'protected':protected}
        infos={};fresh_exists=True
        if cool_ok and cool:
            try:
                infos={m['id']:_cool_info(m) for m in selected}
                fresh_exists=any(not infos[mid]['recent'] for mid in infos) if infos else True
                # Stable re-sort: recently-injected, non-protected memories fall behind fresh
                # ones; the reranker order from (b) is preserved within each group.
                selected.sort(key=lambda m:(0,0) if infos.get(m['id'],{}).get('protected') else (1 if infos.get(m['id'],{}).get('recent') else 0,infos.get(m['id'],{}).get('hits',0)))
            except Exception as e:
                degraded.append('cooldown_sort:'+type(e).__name__);infos={};cool_ok=False
        with self.connect() as db:
            for m in selected:
                if len(returned)>=limit:break
                v=digest(m['content_hash']+str(m.get('summary'))+m['version_status'])
                # (a) graded cooldown: only drop when over-repeated (hits>=3), unprotected, and a
                # fresher candidate exists; otherwise the memory is merely deprioritized above.
                if mode=='auto' and cool_ok:
                    ci=infos.get(m['id']) or _cool_info(m)
                    if ci['recent'] and ci['hits']>=3 and not ci['protected'] and fresh_exists:
                        omitted.append(m['id']);continue
                elif mode=='auto' and session:
                    previous=db.execute('SELECT version,seen_at FROM memory_seen WHERE session_key=? AND memory_id=?',(session,m['id'])).fetchone()
                    if previous and previous['version']==v and time.time()-previous['seen_at']<1800:
                        omitted.append(m['id']);continue
                # (c) tiered injection: pick a tier by confidence, then greedily downgrade to fit.
                conf=0.0
                try:
                    rr=m.get('rerank_score');ss=m.get('semantic_score')
                    conf=max(float(rr) if isinstance(rr,(int,float)) and not isinstance(rr,bool) else 0.0,float(ss) if isinstance(ss,(int,float)) and not isinstance(ss,bool) else 0.0)
                except Exception:conf=0.0
                tier_order=['full','summary','light'];start=0 if conf>=0.6 else (1 if conf>=0.3 else 2)
                for ti in range(start,len(tier_order)):
                    try:b=self._render(m,tier_order[ti])
                    except Exception:b=self.brief(m)
                    cost=tokens(b)
                    if used+cost<=budget:
                        returned.append(b);used+=cost;break
                # Mark only after bridge confirms delivery through /recall/commit.
            # (d) behaviour-independent rule/preference channel: inject a few high-importance
            # procedural memories that text recall may miss, on an isolated ~250-token budget.
            if mode=='auto':
                try:
                    have={x['id'] for x in returned};rule_used=0;rule_added=0
                    rule_rows=db.execute("SELECT m.*,x.layer FROM memories m JOIN memory_meta x ON x.memory_id=m.id WHERE m.namespace=? AND m.version_status='current' AND x.layer='procedural' AND (m.pinned=1 OR m.importance>=0.8) ORDER BY m.pinned DESC,m.importance DESC LIMIT 8",(ns,)).fetchall()
                    for r in rule_rows:
                        if rule_added>=3:break
                        rm=self._row(r)
                        if rm['id'] in have:continue
                        ci=_cool_info(rm) if cool_ok else {'recent':False,'hits':0}
                        if ci.get('recent') and ci.get('hits',0)>=3:continue
                        rb=self._render(rm,'light');rb['channel']='rule';cost=tokens(rb)
                        if rule_used+cost>250:continue
                        returned.append(rb);rule_used+=cost;used+=cost;rule_added+=1;selected.append(rm)
                except Exception as e:
                    degraded.append('rule_channel:'+type(e).__name__)
            rid='rec_'+uuid.uuid4().hex
            diagnostic=[{'id':m['id'],'score':m.get('score'),'semantic_score':m.get('semantic_score'),'lexical_hit':m.get('lexical_hit'),'retrieval_channels':m.get('retrieval_channels',[]),'graph_depth':m.get('graph_depth',0),'path_score':m.get('path_score'),'rerank_score':m.get('rerank_score'),'reviewed':m.get('reviewed',False),'reason':m.get('selection_reason','')} for m in pool]
            chosen=[{'id':m['id'],'reason':m.get('selection_reason',''),'returned':m['id'] in {x['id'] for x in returned},'context_ids':[x['id'] for x in m.get('path',[])],'version':digest(m['content_hash']+str(m.get('summary'))+m['version_status'])} for m in selected]
            db.execute('INSERT INTO recall_log VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(rid,now_iso(),ns,session,q,mode,reason+(' | '+','.join(degraded) if degraded else ''),json.dumps(diagnostic,ensure_ascii=False),json.dumps(chosen,ensure_ascii=False),used,int((time.monotonic()-start)*1000),json.dumps(usage)))
        affect=None
        if affect_future:
            try:affect=affect_future.result(timeout=max(.1,30-(time.monotonic()-start)))
            except Exception:affect=self.affect.snapshot(ns)
        if mode=='explicit':
            touch_ids=list(dict.fromkeys(x for m in returned for x in ([m['id']]+[s['id'] for s in m.get('path',[])])))
            self.retention.touch(touch_ids,rid)
        vector_mode='qdrant_hnsw_with_sqlite_exact_fallback' if self.vector_index.enabled else 'sqlite_exact_embedding'
        return {'affect':affect,'memories':returned,'recall_id':rid,'estimated_tokens':used,'reason':reason,'degraded':degraded,'already_present_ids':omitted,'retrieval':{'lexical':'sqlite_fts5','vector':vector_mode,'graph':'bounded_best_path','max_graph_depth':max(0,min(3,int(args.get('graph_depth',3))))},'primary_model_calls':0}

    def commit_recall(self,rid):
        with self.connect() as db:
            r=db.execute('SELECT * FROM recall_log WHERE id=?',(rid,)).fetchone()
            if not r or not r['session_key']:return {'committed':0}
            used_ids=[];n=0
            for m in json.loads(r['selected_json']):
                if m.get('returned'):
                    used_ids.extend(m.get('context_ids') or [m['id']])
                    # (a) increment hits for cooldown de-weighting; reset when the version changed.
                    prev=db.execute('SELECT version,hits FROM memory_seen WHERE session_key=? AND memory_id=?',(r['session_key'],m['id'])).fetchone()
                    hits=((prev['hits'] if prev and prev['version']==m['version'] else 0) or 0)+1
                    db.execute('INSERT OR REPLACE INTO memory_seen(session_key,memory_id,version,seen_at,hits) VALUES(?,?,?,?,?)',(r['session_key'],m['id'],m['version'],time.time(),hits));n+=1
        self.retention.touch(list(dict.fromkeys(used_ids)),'recall:'+rid)
        return {'committed':n}

    def reset_seen(self,session):
        with self.connect() as db:db.execute('DELETE FROM memory_seen WHERE session_key=?',(session,))
        return {'reset':True}

    def recall(self,query,namespace='default',limit=4,include_history=False,bump=False):
        return self.recall_pack({'query':query,'namespace':namespace,'limit':limit,'include_history':include_history})['memories']

    def boot(self,ns='default',budget=700):
        self.retention.sweep()
        # (d) also make high-importance procedural rules/preferences part of the once-per-session
        # boot injection so they are present even when no user text matches them.
        with self.connect() as db:rows=db.execute("SELECT m.*,x.layer FROM memories m JOIN memory_meta x ON x.memory_id=m.id WHERE m.namespace=? AND m.version_status='current' AND (m.pinned=1 OR x.layer='core' OR (x.layer='procedural' AND (m.pinned=1 OR m.importance>=0.8))) ORDER BY CASE WHEN m.source='system_prompt_migration' THEN 0 ELSE 1 END,m.pinned DESC,m.importance DESC LIMIT 15",(ns,)).fetchall()
        items=[];cost=0
        for r in rows:
            m=self.brief(self._row(r))
            if r['source']=='system_prompt_migration':m['text']=r['content']
            c=tokens(m)
            if c+cost<=budget:items.append(m);cost+=c
        return {'memories':items,'estimated_tokens':cost,'revision':digest(json.dumps(items,ensure_ascii=False,sort_keys=True))}

    def overview(self,ns='default'):
        with self.connect() as db:
            counts={r[0]:r[1] for r in db.execute('SELECT version_status,count(*) FROM memories WHERE namespace=? GROUP BY version_status',(ns,))}
            layers={r[0]:r[1] for r in db.execute('SELECT x.layer,count(*) FROM memory_meta x JOIN memories m ON m.id=x.memory_id WHERE m.namespace=? GROUP BY x.layer',(ns,))}
            jobs=[dict(r) for r in db.execute('SELECT id,kind,status,attempts,created_at,updated_at,result_json,error FROM memory_jobs ORDER BY created_at DESC LIMIT 30')]
            for j in jobs:j['result']=json.loads(j.pop('result_json') or '{}')
            metrics=dict(db.execute('SELECT count(*) calls,coalesce(sum(tokens),0) tokens,coalesce(round(avg(latency_ms)),0) latency_ms FROM recall_log WHERE namespace=? AND created_at>=?',(ns,now_iso()[:10])).fetchone())
            extras={}
            for k,q in {'events':'SELECT count(*) FROM raw_events WHERE namespace=?','evidence':'SELECT count(*) FROM memory_evidence e JOIN memories m ON m.id=e.memory_id WHERE m.namespace=?','vectors':'SELECT count(*) FROM memory_vectors v JOIN memories m ON m.id=v.memory_id WHERE m.namespace=?','links':'SELECT count(*) FROM memory_links l JOIN memories m ON m.id=l.from_id WHERE m.namespace=?'}.items():extras[k]=db.execute(q,(ns,)).fetchone()[0]
            projected=db.execute("SELECT count(*) FROM memory_projection_state p JOIN memories m ON m.id=p.memory_id WHERE p.backend='qdrant' AND m.namespace=?",(ns,)).fetchone()[0]
            extras['vector_projection']={'backend':'qdrant' if self.vector_index.enabled else 'sqlite_exact','indexed':projected,'configured':self.vector_index.enabled}
            progress={'jobs':{r[0]:r[1] for r in db.execute('SELECT status,count(*) FROM memory_jobs GROUP BY status')}}
            cursor=db.execute("SELECT value_json FROM memory_state WHERE key='event_cursor'").fetchone()
            progress['unscanned_events']=db.execute('SELECT count(*) FROM raw_events WHERE namespace=? AND rowid>?',(ns,int(json.loads(cursor[0])) if cursor else 0)).fetchone()[0]
            progress['summarized']=db.execute("SELECT count(*) FROM memories WHERE namespace=? AND summary!=''",(ns,)).fetchone()[0]
            progress['indexable']=db.execute("SELECT count(*) FROM memories WHERE namespace=? AND version_status IN ('current','candidate')",(ns,)).fetchone()[0]
        return {'counts':counts,'layers':layers,**extras,'today':metrics,'jobs':jobs,'progress':progress,'models':{'embedding':self.models.embed_model,'worker':self.models.worker_model,'reviewer':self.models.judge_model,'reranker':getattr(self.models,'rerank_model','unavailable')},'primary_model_calls':0}

    def recalls(self,ns='default',offset=0,limit=30):
        with self.connect() as db:rows=db.execute('SELECT * FROM recall_log WHERE namespace=? ORDER BY created_at DESC LIMIT ? OFFSET ?',(ns,min(100,limit),max(0,offset))).fetchall()
        out=[]
        for r in rows:
            d=dict(r)
            for k in ('candidates','selected','model_usage'):d[k]=json.loads(d.pop(k+'_json') or '{}')
            out.append(d)
        return {'items':out}

    def review(self,mid,action,replaces_id=None):
        m=super().get(mid)
        if not m:raise KeyError('memory_not_found')
        with self.connect() as db:
            if action=='replace':
                db.execute('BEGIN IMMEDIATE')
                current=db.execute('SELECT * FROM memories WHERE id=?',(mid,)).fetchone()
                old=db.execute('SELECT * FROM memories WHERE id=?',(replaces_id,)).fetchone()
                if not old or not current or current['version_status']!='candidate' or old['version_status']!='current' or mid==replaces_id or not current['fact_key'] or old['namespace']!=current['namespace'] or old['fact_key']!=current['fact_key']:
                    raise ValueError('冲突状态已改变，请刷新后重新核对')
                ts=now_iso()
                db.execute("UPDATE memories SET version_status='superseded',superseded_at=?,superseded_by_id=?,updated_at=? WHERE id=?",(ts,mid,ts,replaces_id))
                db.execute("UPDATE memories SET version_status='current',supersedes_id=?,updated_at=? WHERE id=?",(replaces_id,ts,mid))
                db.execute("UPDATE conflict_reviews SET status='superseded',resolved_at=? WHERE candidate_id=? AND existing_id=?",(ts,mid,replaces_id))
                db.execute('INSERT OR REPLACE INTO memory_links VALUES(?,?,?,?,?)',(mid,replaces_id,'updates',1.0,'owner_review'))
            elif action=='approve':
                if m['version_status']!='candidate':raise ValueError('only_candidates_can_be_approved')
                if m.get('fact_key') and db.execute("SELECT 1 FROM memories WHERE namespace=? AND fact_key=? AND version_status='current' AND id!=?",(m['namespace'],m['fact_key'],mid)).fetchone():raise ValueError('conflict_requires_explicit_supersede')
                db.execute("UPDATE memories SET version_status='current',updated_at=? WHERE id=?",(now_iso(),mid))
            elif action=='reject':db.execute("UPDATE memories SET version_status='archived',updated_at=? WHERE id=?",(now_iso(),mid))
            else:raise ValueError('unknown_review_action')
            db.execute('UPDATE memory_meta SET review_status=?,updated_at=? WHERE memory_id=?',(action,now_iso(),mid));self._audit(db,'review_'+action,mid,{})
        return {'id':mid,'action':action}
