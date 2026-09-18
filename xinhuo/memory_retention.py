"""Thirty idle days of grace, then one weight point per thirty idle days.
Retrieval delivery freezes the remaining weight; browsing and curation do not.
"""
import json,time,uuid
from memory_core import now_iso
DAY=86400
GRACE=30*DAY
POINT_PERIOD=30*DAY
SCHEMA='''
CREATE TABLE IF NOT EXISTS memory_retention(memory_id TEXT PRIMARY KEY REFERENCES memories(id),weight REAL NOT NULL,last_used_at REAL NOT NULL,checkpoint_at REAL NOT NULL,dusted_at TEXT);
CREATE TABLE IF NOT EXISTS memory_usage_receipts(receipt TEXT PRIMARY KEY,created_at TEXT NOT NULL);
'''

def remaining(row,at):
    start=max(row['checkpoint_at'],row['last_used_at']+GRACE)
    return max(0.,round(row['weight']-max(0.,at-start)/POINT_PERIOD,6))

class Retention:
    def __init__(self,store,clock=time.time):
        self.s=store;self.clock=clock
        with store.connect() as db:db.executescript(SCHEMA)
        self.seed()

    def seed(self):
        # Old retrieval tracking was incomplete. Start a full, explicit grace
        # period at migration rather than guessing inactivity from creation age.
        at=self.clock()
        with self.s.connect() as db:db.execute('INSERT OR IGNORE INTO memory_retention SELECT id,min(5,max(0,strength)),?,?,NULL FROM memories',(at,at))

    def state(self,mid,at=None):
        with self.s.connect() as db:r=db.execute('SELECT * FROM memory_retention WHERE memory_id=?',(mid,)).fetchone()
        if not r:return None
        at=self.clock() if at is None else at;weight=remaining(r,at)
        return {'weight':round(weight,3),'last_used_at':r['last_used_at'],'decay_starts_at':r['last_used_at']+GRACE,'zero_at':max(r['checkpoint_at'],r['last_used_at']+GRACE)+r['weight']*POINT_PERIOD,'dusted_at':r['dusted_at'],'phase':'dusted' if r['dusted_at'] else ('protected' if at<=r['last_used_at']+GRACE else 'fading')}

    def touch(self,ids,receipt=None):
        self.seed();at=self.clock();n=0
        with self.s.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if receipt:
                if db.execute('SELECT 1 FROM memory_usage_receipts WHERE receipt=?',(receipt,)).fetchone():return {'used':0,'duplicate':True}
                db.execute('INSERT INTO memory_usage_receipts VALUES(?,?)',(receipt,now_iso()))
            for mid in set(ids):
                r=db.execute("SELECT r.* FROM memory_retention r JOIN memories m ON m.id=r.memory_id WHERE r.memory_id=? AND m.version_status='current'",(mid,)).fetchone()
                if not r:continue
                weight=remaining(r,at)
                if weight<=0:continue
                db.execute('UPDATE memory_retention SET weight=?,last_used_at=?,checkpoint_at=? WHERE memory_id=?',(weight,at,at,mid))
                db.execute('UPDATE memories SET last_recalled_at=?,recall_count=recall_count+1 WHERE id=?',(now_iso(),mid));n+=1
        return {'used':n}

    def sweep(self):
        self.seed();at=self.clock();ids=[]
        with self.s.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for r in db.execute("SELECT r.* FROM memory_retention r JOIN memories m ON m.id=r.memory_id WHERE m.version_status='current'").fetchall():
                if remaining(r,at)>0:continue
                mid=r['memory_id'];stamp=now_iso();ids.append(mid)
                db.execute("UPDATE memories SET version_status='dusted',updated_at=? WHERE id=?",(stamp,mid))
                db.execute('UPDATE memory_retention SET weight=0,checkpoint_at=?,dusted_at=? WHERE memory_id=?',(at,stamp,mid))
                self.s._audit(db,'memory_dusted',mid,{'reason':'30_days_grace_then_one_point_per_30_days'})
        return {'dusted':len(ids)}

    def restore(self,mid):
        at=self.clock()
        with self.s.connect() as db:
            db.execute('BEGIN IMMEDIATE');m=db.execute('SELECT * FROM memories WHERE id=?',(mid,)).fetchone()
            if not m or m['version_status']!='dusted':raise ValueError('only_dusted_memory_can_restore')
            conflict=m['fact_key'] and db.execute("SELECT id FROM memories WHERE namespace=? AND fact_key=? AND id!=? AND version_status='current'",(m['namespace'],m['fact_key'],mid)).fetchone()
            status='candidate' if conflict else 'current'
            db.execute('UPDATE memories SET version_status=?,updated_at=? WHERE id=?',(status,now_iso(),mid))
            db.execute('UPDATE memory_retention SET weight=1,last_used_at=?,checkpoint_at=?,dusted_at=NULL WHERE memory_id=?',(at,at,mid))
            self.s._audit(db,'memory_restored',mid,{'weight':1,'status':status})
        return {'id':mid,'status':status,'weight':1,'grace_days':30}
