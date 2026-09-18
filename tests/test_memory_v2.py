import tempfile,unittest,json,os
from memory_core import MemoryStore as LegacyStore
from memory_v2 import MemoryStore
from memory_worker import Worker
class Models:
    embed_model='test';worker_model='test';judge_model='test'
    def __init__(self):self.calls=0;self.fail=False
    def query_vector(self,q):
        if self.fail:raise RuntimeError('unavailable')
        return [1,0]
    def embed(self,txts,timeout=12):return [[1,0] for t in txts]
    def json(self,instruction,data,**kw):
        self.calls+=1
        if self.fail:raise RuntimeError('unavailable')
        if 'candidates' in data and 'question' in data:return {'selected':[{'id':x['id'],'reason':'direct evidence'} for x in data['candidates']]},{}
        return {'memories':[]},{}
class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.models=Models();self.s=MemoryStore(self.tmp.name+'/db',self.tmp.name+'/archive',self.models)
    def tearDown(self):self.tmp.cleanup()
    def add(self,text,**kw):return self.s.upsert({'content':text,**kw})['id']
    def test_migration_preserves_old_records_and_history(self):
        legacy=LegacyStore(self.tmp.name+'/old',self.tmp.name+'/oldarc');x=legacy.upsert({'content':'旧事实','fact_key':'test'})['memory'];legacy.supersede(x['id'],{'content':'新事实'})
        upgraded=MemoryStore(self.tmp.name+'/old',self.tmp.name+'/oldarc',self.models)
        self.assertEqual(upgraded.get(x['id'])['version_status'],'superseded');self.assertEqual(len(upgraded.history('test')),2)
    def test_ack_no_provider_no_pinned_noise(self):
        self.add('身份事实',pinned=True);r=self.s.recall_pack({'query':'好的','mode':'auto'});self.assertFalse(r['memories']);self.assertEqual(self.models.calls,0)
    def test_budget_namespace_history_and_commit(self):
        good=self.add('用户喜欢绿茶',namespace='a')
        self.add('用户喜欢绿茶',namespace='b');old=self.add('过去喜欢绿茶',namespace='a');self.s.archive(old)
        args={'query':'绿茶','namespace':'a','mode':'auto','session_key':'s','budget_tokens':200}
        r=self.s.recall_pack(args);self.assertEqual([m['id'] for m in r['memories']],[good]);self.assertLessEqual(r['estimated_tokens'],200)
        self.assertTrue(self.s.recall_pack(args)['memories']) # uncommitted cancellation must not hide it
        self.s.commit_recall(r['recall_id']);self.assertFalse(self.s.recall_pack(args)['memories']);self.s.reset_seen('s');self.assertTrue(self.s.recall_pack(args)['memories'])
    def test_unavailable_judge_fails_closed_and_observable(self):
        self.add('我喜欢绿茶');self.models.fail=True;r=self.s.recall_pack({'query':'绿茶'});self.assertFalse(r['memories']);self.assertEqual(r['reason'],'review_unavailable');self.assertTrue(r['degraded']);self.assertTrue(self.s.recalls()['items'])
    def test_capsule_string_contract_queues_without_inventing_evidence(self):
        r=self.s.sync_capsule({'capsule':{'about_her':['我喜欢绿茶']},'session_id':'s'});self.assertEqual(r['queued'],1);self.assertEqual(r['written'],0);self.assertEqual(self.s.browse({})['total'],0)
        self.assertEqual(self.s.sync_capsule({'capsule':{'about_her':['我喜欢绿茶']},'session_id':'s'})['job_id'],r['job_id'])
    def test_false_evidence_is_not_promoted(self):
        eid=self.s.ingest_event({'content':'我喜欢绿茶','role':'user','session_id':'s'})['id']
        def false(*a,**kw):return {'memories':[{'content':'用户喜欢咖啡','layer':'semantic','evidence':[{'event_id':eid,'quote':'我喜欢咖啡'}]}]},{}
        self.models.json=false;r=Worker(self.s).extract({'ids':[eid]});self.assertEqual(r['created'],0)
    def test_conflict_does_not_overwrite(self):
        self.add('喜欢绿茶',fact_key='drink');n=self.add('喜欢红茶',fact_key='drink');self.assertEqual(self.s.get(n)['version_status'],'candidate')
        with self.assertRaises(ValueError):self.s.review(n,'approve')
    def test_worker_schedule_bounded_durable_cursor(self):
        for i in range(32):self.s.ingest_event({'content':str(i)+'字'*3998,'role':'user','session_id':'s'})
        w=Worker(self.s);w.schedule()
        with self.s.connect() as db:
            p=json.loads(db.execute("SELECT payload_json FROM memory_jobs WHERE kind='extract'").fetchone()[0]);cur=json.loads(db.execute("SELECT value_json FROM memory_state WHERE key='event_cursor'").fetchone()[0]);self.assertLess(len(p['ids']),32);self.assertEqual(cur,len(p['ids']))
    def test_pagination_all_statuses_and_fulltext(self):
        x=self.add('完整的一条记忆');self.s.archive(x);self.assertEqual(self.s.browse({})['total'],0);self.assertEqual(self.s.browse({'status':'all'})['items'][0]['content'],'完整的一条记忆')
    def test_partial_enrichment_advances_without_duplicate_vectors(self):
        ids=[self.add('索引记录 '+str(i)) for i in range(3)]
        def partial(instruction,data,**kw):
            if 'items' in data and 'content' in data['items'][0]:
                m={'id':ids[0],'summary':'索引记录 0','layer':'semantic','entities':[]}
                return {'items':[m,m]},{}
            if 'items' in data:return {'approved_ids':[ids[0]]},{}
            return {'relations':[]},{}
        self.models.json=partial;r=Worker(self.s).enrich(ids)
        self.assertEqual(r['indexed'],1);self.assertEqual(r['deferred'],2)
        Worker(self.s).schedule()
        with self.s.connect() as db:
            pending=json.loads(db.execute("SELECT payload_json FROM memory_jobs WHERE kind='enrich_batch'").fetchone()[0])['ids']
            self.assertEqual(set(pending),set(ids[1:]));self.assertEqual(db.execute('SELECT count(*) FROM memory_vectors').fetchone()[0],1)
    def test_oversized_legacy_batch_splits_durably_without_losing_events(self):
        ids=[self.s.ingest_event({'content':str(i)+'字'*3000,'role':'user','session_id':'s'})['id'] for i in range(14)]
        result=Worker(self.s).extract({'ids':ids});self.assertGreater(result['split_jobs'],1);self.assertEqual(self.models.calls,0)
        with self.s.connect() as db:
            saved=[i for r in db.execute("SELECT payload_json FROM memory_jobs WHERE kind='extract'") for i in json.loads(r[0])['ids']]
            self.assertEqual(set(saved),set(ids));self.assertEqual(len(saved),len(ids))
    def test_live_ingress_is_durable_and_prioritized_over_backfill(self):
        eid=self.s.ingest_event({'content':'刚才把钥匙给小林了','role':'user','session_id':'s','source_msg_id':'u1'})['id']
        self.s.enqueue('enrich_batch',{'ids':[]});job=Worker(self.s).claim()
        self.assertEqual(job['kind'],'affect_event');self.assertEqual(json.loads(job['payload_json'])['id'],eid)
        job=Worker(self.s).claim();self.assertEqual(job['kind'],'live_extract');self.assertEqual(json.loads(job['payload_json'])['focus_ids'],[eid])
    def test_replace_promotes_existing_candidate_and_preserves_history(self):
        old=self.add('喜欢绿茶',fact_key='drink');new=self.add('喜欢红茶',fact_key='drink')
        self.assertEqual(self.s.get(new)['conflicts'][0]['id'],old)
        self.s.review(new,'replace',old);self.assertEqual(self.s.get(new)['version_status'],'current');self.assertEqual(self.s.get(old)['superseded_by_id'],new)
        self.assertEqual(len(self.s.history('drink')),2)
        with self.assertRaises(ValueError):self.s.review(new,'replace',old)
if __name__=='__main__':unittest.main()
