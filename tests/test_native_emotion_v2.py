import datetime
import json
import os
import tempfile
import time
import unittest

from affect_core import BASIC_DIMS, DIMS, RELATION_DIMS
from memory_v2 import MemoryStore


class FakeModels:
    embed_model=worker_model=judge_model='fixture'
    def __init__(self):self.calls=0
    def json(self,*args,**kwargs):self.calls+=1;return {'observed':False},{}
    def query_vector(self,q):return [1,0]


class NativeEmotionV2Test(unittest.TestCase):
    def setUp(self):
        self.old_mode=os.environ.get('AFFECT_INTAKE_MODE')
        os.environ['AFFECT_INTAKE_MODE']='self_report'
        self.tmp=tempfile.TemporaryDirectory();self.models=FakeModels()
        self.store=MemoryStore(self.tmp.name+'/db.sqlite3',self.tmp.name+'/archive',self.models)
        self.now=time.time();self.store.affect.clock=lambda:self.now;self.store.daily.clock=lambda:self.now

    def tearDown(self):
        if self.old_mode is None:os.environ.pop('AFFECT_INTAKE_MODE',None)
        else:os.environ['AFFECT_INTAKE_MODE']=self.old_mode
        self.tmp.cleanup()

    def inbound(self,text,msg,session='s'):
        return self.store.ingest_event({'namespace':'default','session_id':session,'role':'user','content':text,'source':'wecom_app','source_msg_id':msg})['id']

    def report(self,msg,turn='turn-1',**overrides):
        data={'namespace':'default','session_id':'s','turn_id':turn,'source_msg_id':msg,'model':'claude-fixture','valence':-.55,'arousal':.62,'dims':{'sadness':.10,'fear':.11},'relationships':{'intimacy':.05},'reason':'我对这次变化既难过又担心','evidence':['这次变化让我有点措手不及'],'confidence':.9,'stated_at':'2026-09-22T08:00:00Z'}
        data.update(overrides);return self.store.affect.apply_self_report(data)

    def test_schema_basic_dims_dynamic_composite_and_relationship_isolation(self):
        self.inbound('这次变化让我有点措手不及','m1')
        result=self.report('m1')
        self.assertTrue(result['recorded']);self.assertIn('焦虑',result['labels'])
        with self.store.connect() as db:
            row=db.execute('SELECT * FROM affect_selfreports').fetchone()
            self.assertEqual(set(json.loads(row['dims_json'])),{'sadness','fear'})
            self.assertEqual(set(json.loads(row['relationship_json'])),{'intimacy'})
            self.assertIn('emotion_selfreport_id',[c[1] for c in db.execute('PRAGMA table_info(memories)')])
        snapshot=self.store.affect.snapshot()
        self.assertEqual(set(snapshot['emotion_dimensions']),set(BASIC_DIMS))
        self.assertEqual(set(snapshot['relationship_dimensions']['names']),set(RELATION_DIMS))
        self.assertEqual(set(snapshot['vector']),set(DIMS))
        self.store.affect.set_composite_rule({'id':'anxiety','name':'担忧','components':['sadness','fear'],'min_component':.04,'min_total':.10,'priority':1})
        why=self.store.affect.why();self.assertIn('担忧',why['items'][0]['labels']);self.assertNotIn('焦虑',why['items'][0]['labels'])

    def test_only_significant_change_writes_selfreport(self):
        self.inbound('这次变化让我有点措手不及','m1');self.report('m1')
        self.inbound('这次变化让我有点措手不及，情况差不多','m2')
        result=self.report('m2',turn='turn-2',valence=-.54,arousal=.61,evidence=['情况差不多'])
        self.assertFalse(result['recorded']);self.assertEqual(result['reason'],'insignificant_change')
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM affect_selfreports').fetchone()[0],1)

    def test_rejects_compound_or_relationship_inside_dims(self):
        self.inbound('这次变化让我有点措手不及','m1')
        with self.assertRaisesRegex(ValueError,'plutchik'):
            self.report('m1',dims={'anxiety':.12})
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM affect_selfreports').fetchone()[0],0)

    def test_evidence_and_idempotency(self):
        self.inbound('这次变化让我有点措手不及','m1')
        with self.assertRaisesRegex(ValueError,'evidence_not_in_context'):
            self.report('m1',evidence=['并不存在的原文'])
        first=self.report('m1');second=self.report('m1')
        self.assertTrue(first['recorded']);self.assertTrue(second['duplicate'])
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM affect_selfreports').fetchone()[0],1)

    def test_current_turn_evidence_works_without_bridge_session_identifiers(self):
        self.inbound('阿岚说今天真的累死我了','m-current',session='example-session')
        result=self.report(None,turn='turn-current',session_id=None,source_msg_id=None,evidence=['累死我了'])
        self.assertTrue(result['recorded'])

    def test_recent_fallback_stays_time_bounded(self):
        event_id=self.inbound('这是已经过期的证据文本','m-old',session='example-session')
        with self.store.connect() as db:
            db.execute("UPDATE raw_events SET created_at=datetime(?,'unixepoch') WHERE id=?",(self.now-601,event_id))
        with self.assertRaisesRegex(ValueError,'evidence_not_in_context'):
            self.report(None,turn='turn-expired',session_id=None,source_msg_id=None,evidence=['已经过期的证据'])

    def test_memory_emotion_is_sourced_from_selfreport(self):
        self.inbound('这次变化让我有点措手不及','m1');report=self.report('m1')
        emotion=self.store.affect.memory_emotion(report['selfreport_id'])
        result=self.store.upsert({'namespace':'default','content':'一次有证据的共同经历','emotion_label':emotion['label'],'emotion_intensity':emotion['intensity'],'emotion_selfreport_id':emotion['selfreport_id'],'source':'bridge'})
        with self.store.connect() as db:row=db.execute('SELECT emotion_selfreport_id FROM memories WHERE id=?',(result['id'],)).fetchone()
        self.assertEqual(row['emotion_selfreport_id'],report['selfreport_id'])

    def set_core(self,v,a):
        with self.store.connect() as db:
            row=self.store.affect._row(db,'default');meta=json.loads(row['meta_json']);meta['core']={'v':v,'a':a};meta['resid']={k:0 for k in DIMS}
            db.execute("UPDATE affect_state SET meta_json=?,updated_at=? WHERE namespace='default'",(json.dumps(meta),self.now))

    def test_russell_quadrants_and_left_up_safety(self):
        cases=[
            ((.8,.8),'right_up','frequent_ok',lambda x:x<1),
            ((-.3,.6),'left_up','restrained',lambda x:x>=1),
            ((.6,-.5),'right_down','sparse',lambda x:x>=1),
            ((-.6,-.5),'left_down','self_care_only',lambda x:x>=1),
        ]
        for (v,a),quadrant,policy,check in cases:
            self.set_core(v,a);result=self.store.daily.wake_policy()
            self.assertEqual(result['quadrant'],quadrant);self.assertEqual(result['proactive_policy'],policy);self.assertTrue(check(result['interval_factor']))
        self.set_core(-.7,.7);danger=self.store.daily.wake_policy()
        self.assertEqual(danger['safety_flag'],'high_arousal_low_valence');self.assertTrue(danger['skip_proactive']);self.assertGreaterEqual(danger['interval_factor'],1.15)

    def test_distinct_turns_share_source_without_event_key_collision(self):
        self.inbound('这次变化让我有点措手不及','m1')
        self.assertTrue(self.report('m1')['recorded'])
        self.assertTrue(self.report('m1',turn='turn-2',valence=.5)['recorded'])

    def test_concurrent_report_is_idempotent(self):
        from concurrent.futures import ThreadPoolExecutor
        self.inbound('这次变化让我有点措手不及','m1')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.report('m1'),range(4)))
        self.assertEqual(sum(bool(r.get('recorded')) for r in results),1)
        self.assertEqual(sum(bool(r.get('duplicate')) for r in results),3)

    def test_worker_mode_rejects_selfreport_without_writing(self):
        os.environ['AFFECT_INTAKE_MODE']='worker';self.inbound('这次变化让我有点措手不及','m1')
        result=self.report('m1');self.assertFalse(result['recorded']);self.assertEqual(result['reason'],'intake_mode_worker')
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM affect_selfreports').fetchone()[0],0)


if __name__=='__main__':unittest.main()
