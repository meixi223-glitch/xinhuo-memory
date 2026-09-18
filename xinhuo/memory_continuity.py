"""Evidence-linked continuity sidecar for Xinhuo memory.

Continuity is historical, derived context. It never changes factual memories,
their versions, retrieval indexes, retention weights, or authorization state.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from memory_core import now_iso, parse_time

KINDS = {"trajectory", "nearfield", "latent"}
SECRET = re.compile(r"(?i)(?:sk-[a-z0-9_-]{18,}|Bearer\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:password|api_key|access_token|refresh_token)\s*[=:]\s*\S+)")
STOP = set("什么 怎么 为什么 这个 那个 一个 我们 你们 他们 现在 今天 事情 可以 知道 觉得 记得 记住 好的 继续 谢谢".split())

SCHEMA = """
CREATE TABLE IF NOT EXISTS continuity_trajectories(
 id TEXT PRIMARY KEY, namespace TEXT NOT NULL, axis_key TEXT NOT NULL,
 title TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('open','paused','resolved')),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(namespace,axis_key));
CREATE TABLE IF NOT EXISTS continuity_trajectory_steps(
 id TEXT PRIMARY KEY, trajectory_id TEXT NOT NULL REFERENCES continuity_trajectories(id),
 summary TEXT NOT NULL, open_question TEXT, observed_at TEXT NOT NULL,
 evidence_hash TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'evidence_verified',
 created_at TEXT NOT NULL, UNIQUE(trajectory_id,evidence_hash));
CREATE TABLE IF NOT EXISTS continuity_trajectory_evidence(
 step_id TEXT NOT NULL REFERENCES continuity_trajectory_steps(id),
 event_id TEXT NOT NULL REFERENCES raw_events(id), quote TEXT NOT NULL,
 PRIMARY KEY(step_id,event_id,quote));
CREATE TABLE IF NOT EXISTS continuity_nearfield_snapshots(
 id TEXT PRIMARY KEY, namespace TEXT NOT NULL, window_start TEXT NOT NULL,
 window_end TEXT NOT NULL, body TEXT NOT NULL, source_hash TEXT NOT NULL UNIQUE,
 generated_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS continuity_nearfield_evidence(
 snapshot_id TEXT NOT NULL REFERENCES continuity_nearfield_snapshots(id),
 event_id TEXT NOT NULL REFERENCES raw_events(id), quote TEXT NOT NULL,
 PRIMARY KEY(snapshot_id,event_id,quote));
CREATE TABLE IF NOT EXISTS continuity_latent_notes(
 id TEXT PRIMARY KEY, namespace TEXT NOT NULL, text TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('review_required','approved','rejected','expired','stale')),
 source_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 expires_at TEXT NOT NULL, reviewed_at TEXT, review_note TEXT);
CREATE TABLE IF NOT EXISTS continuity_latent_evidence(
 note_id TEXT NOT NULL REFERENCES continuity_latent_notes(id),
 event_id TEXT NOT NULL REFERENCES raw_events(id), quote TEXT NOT NULL,
 PRIMARY KEY(note_id,event_id,quote));
CREATE TABLE IF NOT EXISTS continuity_seen(
 session_key TEXT NOT NULL,item_id TEXT NOT NULL,version TEXT NOT NULL,seen_at REAL NOT NULL,
 PRIMARY KEY(session_key,item_id));
CREATE TABLE IF NOT EXISTS continuity_recall_log(
 id TEXT PRIMARY KEY,created_at TEXT NOT NULL,namespace TEXT NOT NULL,session_key TEXT,
 query TEXT,selected_json TEXT,tokens INTEGER,latency_ms INTEGER);
CREATE INDEX IF NOT EXISTS continuity_trajectory_state ON continuity_trajectories(namespace,state,updated_at DESC);
CREATE INDEX IF NOT EXISTS continuity_nearfield_live ON continuity_nearfield_snapshots(namespace,expires_at DESC);
CREATE INDEX IF NOT EXISTS continuity_latent_state ON continuity_latent_notes(namespace,status,updated_at DESC);
"""


def _clean(value, limit=2000):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _terms(value):
    text=str(value or "").lower();out=re.findall(r"[a-z0-9_\-]{2,}",text)
    for run in re.findall(r"[\u3400-\u9fff]+",text):out += [run[i:i+2] for i in range(len(run)-1)]
    return [x for x in out if x not in STOP]


def _tokens(value):
    return math.ceil(len(json.dumps(value,ensure_ascii=False,separators=(",",":" )).encode())/3)+8


def _hash(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


class ContinuityStore:
    def __init__(self, store):
        self.store=store
        with store.connect() as db:
            db.executescript(SCHEMA)
            # A new deployment starts from new events. Historical backfill is a
            # separate, explicit operation so rollout cannot flood the workers.
            if not db.execute("SELECT 1 FROM memory_state WHERE key='continuity_event_cursor'").fetchone():
                cursor=db.execute("SELECT COALESCE(MAX(rowid),0) FROM raw_events").fetchone()[0]
                db.execute("INSERT INTO memory_state(key,value_json) VALUES('continuity_event_cursor',?)",(json.dumps(cursor),))

    def _evidence(self, db, evidence, namespace):
        checked=[]
        for item in list(evidence or [])[:8]:
            if not isinstance(item,dict):raise ValueError("invalid_evidence")
            eid=_clean(item.get("event_id"),100);quote=_clean(item.get("quote"),1200)
            row=db.execute("SELECT id,content,occurred_at,namespace FROM raw_events WHERE id=?",(eid,)).fetchone()
            if not row or row["namespace"]!=namespace or not quote or quote not in row["content"]:raise ValueError("evidence_quote_mismatch")
            checked.append({"event_id":eid,"quote":quote,"occurred_at":row["occurred_at"]})
        if not checked:raise ValueError("evidence_required")
        return checked

    def add_trajectory(self, data):
        ns=str(data.get("namespace") or "default");axis=_clean(data.get("axis_key"),160);title=_clean(data.get("title"),160)
        summary=_clean(data.get("summary"),1000);question=_clean(data.get("open_question"),600)
        if not axis or not title or not summary or SECRET.search(json.dumps(data,ensure_ascii=False)):raise ValueError("invalid_trajectory")
        now=now_iso()
        with self.store.connect() as db:
            evidence=self._evidence(db,data.get("evidence"),ns)
            evhash=_hash(json.dumps([(x["event_id"],x["quote"]) for x in evidence],ensure_ascii=False,sort_keys=True)+summary+question)
            row=db.execute("SELECT id FROM continuity_trajectories WHERE namespace=? AND axis_key=?",(ns,axis)).fetchone()
            tid=row["id"] if row else "ctr_"+uuid.uuid4().hex
            if not row:db.execute("INSERT INTO continuity_trajectories VALUES(?,?,?,?,?,?,?)",(tid,ns,axis,title,"open",now,now))
            else:db.execute("UPDATE continuity_trajectories SET title=?,updated_at=? WHERE id=?",(title,now,tid))
            sid="cts_"+uuid.uuid4().hex
            cur=db.execute("INSERT OR IGNORE INTO continuity_trajectory_steps VALUES(?,?,?,?,?,?,?,?)",(sid,tid,summary,question,evidence[0]["occurred_at"],evhash,"evidence_verified",now))
            if not cur.rowcount:return {"status":"existing","trajectory_id":tid}
            for e in evidence:db.execute("INSERT INTO continuity_trajectory_evidence VALUES(?,?,?)",(sid,e["event_id"],e["quote"]))
            self.store._audit(db,"continuity_trajectory_step",None,{"trajectory_id":tid,"step_id":sid})
        return {"status":"created","trajectory_id":tid,"step_id":sid}

    def add_nearfield(self, data):
        ns=str(data.get("namespace") or "default");body=_clean(data.get("body"),1800)
        if not body or SECRET.search(json.dumps(data,ensure_ascii=False)):raise ValueError("invalid_nearfield")
        now=datetime.now(timezone.utc);ttl=max(3,min(7,int(data.get("ttl_days",7))))
        with self.store.connect() as db:
            evidence=self._evidence(db,data.get("evidence"),ns);latest=max(parse_time(x["occurred_at"]) for x in evidence);expires=latest+timedelta(days=ttl)
            if expires<=now:return {"status":"stale","reason":"nearfield_source_expired"}
            source_hash=_hash(json.dumps([(x["event_id"],x["quote"]) for x in evidence],ensure_ascii=False,sort_keys=True)+body)
            nid="cnf_"+uuid.uuid4().hex
            cur=db.execute("INSERT OR IGNORE INTO continuity_nearfield_snapshots VALUES(?,?,?,?,?,?,?,?)",(nid,ns,min(x["occurred_at"] for x in evidence),max(x["occurred_at"] for x in evidence),body,source_hash,now.isoformat(),expires.isoformat()))
            if not cur.rowcount:return {"status":"existing"}
            for e in evidence:db.execute("INSERT INTO continuity_nearfield_evidence VALUES(?,?,?)",(nid,e["event_id"],e["quote"]))
            self.store._audit(db,"continuity_nearfield_added",None,{"snapshot_id":nid})
        return {"status":"created","id":nid,"expires_at":expires.isoformat()}

    def add_latent(self, data):
        ns=str(data.get("namespace") or "default");text=_clean(data.get("text"),500)
        if not text or SECRET.search(json.dumps(data,ensure_ascii=False)):raise ValueError("invalid_latent")
        now=datetime.now(timezone.utc);expires=now+timedelta(days=max(3,min(30,int(data.get("ttl_days",15)))))
        with self.store.connect() as db:
            evidence=self._evidence(db,data.get("evidence"),ns);source_hash=_hash(json.dumps([(x["event_id"],x["quote"]) for x in evidence],ensure_ascii=False,sort_keys=True)+text)
            lid="cln_"+uuid.uuid4().hex
            cur=db.execute("INSERT OR IGNORE INTO continuity_latent_notes VALUES(?,?,?,?,?,?,?,?,?,?)",(lid,ns,text,"review_required",source_hash,now.isoformat(),now.isoformat(),expires.isoformat(),None,None))
            if not cur.rowcount:return {"status":"existing"}
            for e in evidence:db.execute("INSERT INTO continuity_latent_evidence VALUES(?,?,?)",(lid,e["event_id"],e["quote"]))
            self.store._audit(db,"continuity_latent_proposed",None,{"note_id":lid})
        return {"status":"review_required","id":lid}

    def review_latent(self, item_id, action, note="", namespace="default"):
        if action not in {"approve","reject"}:raise ValueError("invalid_review_action")
        status={"approve":"approved","reject":"rejected"}[action];now=now_iso()
        with self.store.connect() as db:
            row=db.execute("SELECT status,expires_at FROM continuity_latent_notes WHERE id=? AND namespace=?",(item_id,namespace)).fetchone()
            if not row:raise KeyError("latent_not_found")
            if row["status"]!="review_required":raise ValueError("latent_already_reviewed")
            if parse_time(row["expires_at"])<=datetime.now(timezone.utc):status="expired"
            db.execute("UPDATE continuity_latent_notes SET status=?,updated_at=?,reviewed_at=?,review_note=? WHERE id=? AND namespace=?",(status,now,now,_clean(note,300),item_id,namespace))
            self.store._audit(db,"continuity_latent_"+status,None,{"note_id":item_id})
        return {"id":item_id,"status":status}

    def set_trajectory_state(self, item_id, state, namespace="default"):
        if state not in {"open","paused","resolved"}:raise ValueError("invalid_trajectory_state")
        with self.store.connect() as db:
            cur=db.execute("UPDATE continuity_trajectories SET state=?,updated_at=? WHERE id=? AND namespace=?",(state,now_iso(),item_id,namespace))
            if not cur.rowcount:raise KeyError("trajectory_not_found")
            self.store._audit(db,"continuity_trajectory_"+state,None,{"trajectory_id":item_id})
        return {"id":item_id,"state":state}

    def list(self, kind, namespace="default", status="", limit=30, include_evidence=False):
        if kind not in KINDS:raise ValueError("invalid_continuity_kind")
        limit=max(1,min(100,int(limit)));now=now_iso()
        with self.store.connect() as db:
            if kind=="trajectory":
                where="t.namespace=?";args=[namespace]
                if status:where+=" AND t.state=?";args.append(status)
                rows=db.execute("SELECT t.*,s.id step_id,s.summary,s.open_question,s.observed_at FROM continuity_trajectories t LEFT JOIN continuity_trajectory_steps s ON s.id=(SELECT id FROM continuity_trajectory_steps WHERE trajectory_id=t.id ORDER BY observed_at DESC,created_at DESC LIMIT 1) WHERE "+where+" ORDER BY t.updated_at DESC LIMIT ?",args+[limit]).fetchall()
            elif kind=="nearfield":
                rows=db.execute("SELECT * FROM continuity_nearfield_snapshots WHERE namespace=? AND expires_at>? ORDER BY window_end DESC LIMIT ?",(namespace,now,limit)).fetchall()
            else:
                where="namespace=?";args=[namespace]
                if status:where+=" AND status=?";args.append(status)
                if status in {"review_required","approved"}:where+=" AND expires_at>?";args.append(now)
                rows=db.execute("SELECT * FROM continuity_latent_notes WHERE "+where+" ORDER BY updated_at DESC LIMIT ?",args+[limit]).fetchall()
            out=[dict(x) for x in rows]
            if include_evidence:
                for item in out:
                    table,key=("continuity_trajectory_evidence","step_id") if kind=="trajectory" else (("continuity_nearfield_evidence","snapshot_id") if kind=="nearfield" else ("continuity_latent_evidence","note_id"))
                    ref=item.get("step_id") if kind=="trajectory" else item["id"]
                    item["evidence"]=[dict(x) for x in db.execute(f"SELECT event_id,quote FROM {table} WHERE {key}=?",(ref,))]
        return out

    def pack(self, args, record_recall=True):
        start=time.monotonic();q=_clean(args.get("query"),1600);ns=str(args.get("namespace") or "default");session=_clean(args.get("session_key"),200)
        budget=max(120,min(600,int(args.get("budget_tokens",450))));limit=max(1,min(4,int(args.get("limit",3))));now=now_iso();query_terms=set(_terms(q+" "+_clean(args.get("context"),600)))
        candidates=[]
        for kind in ("trajectory","nearfield","latent"):
            state="open" if kind=="trajectory" else ("approved" if kind=="latent" else "")
            for item in self.list(kind,ns,state,20,False):
                text=item.get("summary") or item.get("body") or item.get("text") or "";title=item.get("title") or ""
                overlap=len(query_terms & set(_terms(title+" "+text))) if query_terms else 0
                if kind=="latent" and overlap==0:continue
                score=overlap*4+({"trajectory":3,"nearfield":2,"latent":1}[kind])
                candidates.append((score,item.get("updated_at") or item.get("window_end") or item.get("created_at") or "",kind,item))
        candidates.sort(key=lambda x:(x[0],x[1]),reverse=True);selected=[];used=0
        with self.store.connect() as db:
            for _,_,kind,item in candidates:
                version=_hash(json.dumps(item,ensure_ascii=False,sort_keys=True));seen=db.execute("SELECT version,seen_at FROM continuity_seen WHERE session_key=? AND item_id=?",(session,item["id"])).fetchone() if session else None
                if seen and seen["version"]==version and time.time()-seen["seen_at"]<1800:continue
                compact={"id":item["id"],"kind":kind,"title":item.get("title"),"text":item.get("summary") or item.get("body") or item.get("text"),"open_question":item.get("open_question"),"observed_at":item.get("observed_at") or item.get("window_end") or item.get("created_at"),"expires_at":item.get("expires_at"),"historical_derived":True,"version":version}
                cost=_tokens(compact)
                if used+cost>budget or len(selected)>=limit:continue
                selected.append(compact);used+=cost
            rid="conrec_"+uuid.uuid4().hex if record_recall else None
            if rid:
                db.execute("INSERT INTO continuity_recall_log VALUES(?,?,?,?,?,?,?,?)",(rid,now,ns,session,q,json.dumps(selected,ensure_ascii=False),used,int((time.monotonic()-start)*1000)))
        return {"items":selected,"continuity_recall_id":rid,"estimated_tokens":used,"budget_tokens":budget,"historical_derived":True}

    def commit(self, recall_id):
        with self.store.connect() as db:
            row=db.execute("SELECT session_key,selected_json FROM continuity_recall_log WHERE id=?",(recall_id,)).fetchone()
            if not row or not row["session_key"]:return {"committed":0}
            items=json.loads(row["selected_json"]);now=time.time()
            for item in items:db.execute("INSERT OR REPLACE INTO continuity_seen VALUES(?,?,?,?)",(row["session_key"],item["id"],item["version"],now))
        return {"committed":len(items)}

    def reset_seen(self, session_key):
        with self.store.connect() as db:db.execute("DELETE FROM continuity_seen WHERE session_key=?",(str(session_key or ""),))
        return {"reset":True}

    def status(self, namespace="default"):
        with self.store.connect() as db:
            now=now_iso()
            return {"namespace":namespace,"trajectory":dict(db.execute("SELECT count(*) total,sum(state='open') open FROM continuity_trajectories WHERE namespace=?",(namespace,)).fetchone()),"nearfield":dict(db.execute("SELECT count(*) total,sum(expires_at>?) active FROM continuity_nearfield_snapshots WHERE namespace=?",(now,namespace)).fetchone()),"latent":dict(db.execute("SELECT count(*) total,sum(status='review_required' AND expires_at>?) review_required,sum(status='approved' AND expires_at>?) approved FROM continuity_latent_notes WHERE namespace=?",(now,now,namespace)).fetchone())}
