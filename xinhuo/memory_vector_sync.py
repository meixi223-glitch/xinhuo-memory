#!/usr/bin/env python3
"""Incrementally project authoritative SQLite vectors into Qdrant."""
import fcntl
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from memory_core import now_iso
from memory_vector_index import QdrantVectorIndex

SCHEMA='''
CREATE TABLE IF NOT EXISTS memory_projection_state(
 backend TEXT NOT NULL,
 memory_id TEXT NOT NULL,
 content_hash TEXT NOT NULL,
 status TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(backend,memory_id)
);
'''

class VectorProjector:
    def __init__(self,db_path,index=None,model=None,batch_size=64,max_rows=None):
        self.db_path=str(db_path);self.index=index or QdrantVectorIndex()
        self.model=str(model or os.getenv('MEMORY_EMBED_MODEL','BAAI/bge-m3'))
        self.batch_size=max(1,min(256,int(batch_size)))
        configured=max_rows if max_rows is not None else os.getenv('MEMORY_VECTOR_SYNC_MAX_ROWS','4096')
        self.max_rows=max(1,min(100000,int(configured)))

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.db_path,timeout=30);db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                db.executescript(SCHEMA);yield db
        finally:db.close()

    def run(self):
        if not self.index.enabled:raise RuntimeError('vector_index_not_configured')
        with self.connect() as db:
            sample=db.execute("""
                SELECT v.vector_json
                FROM memories m JOIN memory_vectors v ON v.memory_id=m.id
                WHERE m.version_status IN ('current','candidate') AND v.model=? AND v.content_hash=m.content_hash
                ORDER BY m.rowid LIMIT 1
            """,(self.model,)).fetchone()
            pending_before=db.execute("""
                SELECT count(*)
                FROM memories m JOIN memory_vectors v ON v.memory_id=m.id
                LEFT JOIN memory_projection_state p ON p.backend='qdrant' AND p.memory_id=m.id
                WHERE m.version_status IN ('current','candidate') AND v.model=? AND v.content_hash=m.content_hash
                  AND (p.memory_id IS NULL OR p.content_hash!=m.content_hash OR p.status!=m.version_status)
            """,(self.model,)).fetchone()[0]
            obsolete_before=db.execute("""
                SELECT count(*) FROM memory_projection_state p
                LEFT JOIN memories m ON m.id=p.memory_id AND m.version_status IN ('current','candidate')
                LEFT JOIN memory_vectors v ON v.memory_id=p.memory_id AND v.model=? AND v.content_hash=m.content_hash
                WHERE p.backend='qdrant' AND (m.id IS NULL OR v.memory_id IS NULL)
            """,(self.model,)).fetchone()[0]
        dimension=len(json.loads(sample['vector_json'])) if sample else 0
        if not dimension and not obsolete_before:return {'indexed':0,'deleted':0,'pending':0,'remaining':0,'status':'no_vectors'}
        created=self.index.ensure_collection(dimension) if dimension else False
        remaining_budget=self.max_rows
        deleted=0
        while remaining_budget:
            with self.connect() as db:
                obsolete=[r[0] for r in db.execute("""
                SELECT p.memory_id FROM memory_projection_state p
                LEFT JOIN memories m ON m.id=p.memory_id AND m.version_status IN ('current','candidate')
                LEFT JOIN memory_vectors v ON v.memory_id=p.memory_id AND v.model=? AND v.content_hash=m.content_hash
                WHERE p.backend='qdrant' AND (m.id IS NULL OR v.memory_id IS NULL)
                ORDER BY p.memory_id LIMIT ?
                """,(self.model,min(self.batch_size,remaining_budget))).fetchall()]
            if not obsolete:break
            deleted+=self.index.delete(obsolete)
            with self.connect() as db:
                db.executemany("DELETE FROM memory_projection_state WHERE backend='qdrant' AND memory_id=?",[(mid,) for mid in obsolete])
            remaining_budget-=len(obsolete)
        indexed=0
        while dimension and remaining_budget:
            with self.connect() as db:
                batch=db.execute("""
                    SELECT m.id,m.namespace,m.version_status,m.content_hash,v.model,v.vector_json
                    FROM memories m JOIN memory_vectors v ON v.memory_id=m.id
                    LEFT JOIN memory_projection_state p ON p.backend='qdrant' AND p.memory_id=m.id
                    WHERE m.version_status IN ('current','candidate') AND v.model=? AND v.content_hash=m.content_hash
                      AND (p.memory_id IS NULL OR p.content_hash!=m.content_hash OR p.status!=m.version_status)
                    ORDER BY m.rowid LIMIT ?
                """,(self.model,min(self.batch_size,remaining_budget))).fetchall()
            if not batch:break
            items=[]
            for row in batch:
                items.append({'memory_id':row['id'],'namespace':row['namespace'],'status':row['version_status'],'content_hash':row['content_hash'],'model':row['model'],'vector':json.loads(row['vector_json'])})
            indexed+=self.index.upsert(items)
            with self.connect() as db:
                db.executemany("INSERT OR REPLACE INTO memory_projection_state VALUES('qdrant',?,?,?,?)",[(r['id'],r['content_hash'],r['version_status'],now_iso()) for r in batch])
            remaining_budget-=len(batch)
        with self.connect() as db:
            pending_after=db.execute("""
                SELECT count(*)
                FROM memories m JOIN memory_vectors v ON v.memory_id=m.id
                LEFT JOIN memory_projection_state p ON p.backend='qdrant' AND p.memory_id=m.id
                WHERE m.version_status IN ('current','candidate') AND v.model=? AND v.content_hash=m.content_hash
                  AND (p.memory_id IS NULL OR p.content_hash!=m.content_hash OR p.status!=m.version_status)
            """,(self.model,)).fetchone()[0]
            obsolete_after=db.execute("""
                SELECT count(*) FROM memory_projection_state p
                LEFT JOIN memories m ON m.id=p.memory_id AND m.version_status IN ('current','candidate')
                LEFT JOIN memory_vectors v ON v.memory_id=p.memory_id AND v.model=? AND v.content_hash=m.content_hash
                WHERE p.backend='qdrant' AND (m.id IS NULL OR v.memory_id IS NULL)
            """,(self.model,)).fetchone()[0]
        remaining=pending_after+obsolete_after
        return {'indexed':indexed,'deleted':deleted,'pending':pending_before,'obsolete':obsolete_before,'remaining':remaining,'capped':remaining>0 and remaining_budget==0,'collection_created':created,'model':self.model,'primary_model_calls':0}

def main():
    root=Path(os.getenv('MEMORY_ROOT','./data'))
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (root/'vector-sync.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        result=VectorProjector(os.getenv('MEMORY_DB',str(root/'memory.sqlite3'))).run()
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))

if __name__=='__main__':main()
