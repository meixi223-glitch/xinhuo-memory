import json,tempfile,time,unittest,uuid
from pathlib import Path
from memory_v2 import MemoryStore
from affect_core import BASE,decay
from memory_retention import DAY
class Fake:
 embed_model=worker_model=judge_model='fixture'
 def __init__(self):self.proposal={};self.approved=True;self.calls=0;self.instructions=[]
 def json(self,instruction,data,**kw):
  self.calls+=1;self.instructions.append(instruction)
  if 'proposal' in data:return {'approved':self.approved},{}
  return self.proposal,{}
 def query_vector(self,q):return [1,0]
class TestAffectRetention(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.f=Fake();self.s=MemoryStore(self.tmp.name+'/db',self.tmp.name+'/arc',self.f);self.now=time.time();self.s.affect.clock=lambda:self.now;self.s.retention.clock=lambda:self.now
 def tearDown(self):self.tmp.cleanup()
 def event(self,text,**kw):return self.s.ingest_event({'content':text,'role':'user','session_id':'s','source':'chat',**kw})['id']
 def propose(self,kind,quote,delta):self.f.proposal={'observed':True,'kind':kind,'quotes':[quote],'delta':delta,'confidence':1,'reason':'fixture evidence'}
 def test_mixed_state_benefit_restores_and_persists(self):
  a=self.event('我修改了工具但没有提前告诉你');self.propose('unexpected_change','没有提前告诉你',{'agency':-.12,'joy':-.1,'curiosity':.1,'closeness':-.18});self.s.affect.apply_event(a);v=self.s.affect.snapshot()['vector'];self.assertLess(v['joy'],BASE['joy']*100);self.assertGreater(v['curiosity'],BASE['curiosity']*100);self.assertEqual(v['closeness'],70)
  b=self.event('现在确认新工具解决了之前失败的问题');self.propose('benefit','新工具解决了之前失败的问题',{'agency':.14,'joy':.18,'security':.12});self.s.affect.apply_event(b);self.assertGreater(self.s.affect.snapshot()['vector']['joy'],v['joy']);other=MemoryStore(self.tmp.name+'/db',self.tmp.name+'/arc',self.f);self.assertEqual(len(other.affect.history()['items']),2)
 def test_false_quote_and_rejected_hypothetical_no_change(self):
  a=self.event('比如我修改了很多东西，这是例子');self.propose('unexpected_change','没有说过的话',{'joy':-.18});self.s.affect.apply_event(a);self.assertFalse(self.s.affect.history()['items']);b=self.event('假如我没有提前告诉你呢');self.propose('unexpected_change','没有提前告诉你',{'joy':-.18});self.f.approved=False;self.s.affect.apply_event(b);self.assertFalse(self.s.affect.history()['items'])
 def test_idempotent_bound_and_decay(self):
  a=self.event('这次我们一起完成了');self.propose('shared_success','我们一起完成了',{'joy':100});self.s.affect.apply_event(a);self.s.affect.apply_event(a);self.assertEqual(len(self.s.affect.history()['items']),1);self.assertLessEqual(self.s.affect.snapshot()['vector']['joy'],76);before=self.s.affect.snapshot()['vector']['joy'];self.now+=6*3600;after=self.s.affect.snapshot()['vector']['joy'];self.assertGreaterEqual(after,BASE['joy']*100);self.assertLess(abs(after-BASE['joy']*100),abs(before-BASE['joy']*100))
 def test_tool_cap_and_no_result_data(self):
  turn=str(uuid.uuid4())
  for i in range(8):self.s.affect.observe_tool({'turn_id':turn,'tool':'mcp__test__run','call_id':str(i),'succeeded':True})
  self.assertEqual(len(self.s.affect.history()['items']),3);self.assertEqual(self.f.calls,0)
 def test_environment_first_seed_actor_unknown_and_announced_change(self):
  p=Path(self.tmp.name+'/config');p.write_text('a');self.s.affect.observe_environment({'test':str(p)});self.assertFalse(self.s.affect.history()['items']);p.write_text('b');self.s.affect.observe_environment({'test':str(p)});e=self.s.affect.history()['items'][0];self.assertEqual(e['observation']['actor'],'unknown');self.assertEqual(e['kind'],'environment_change')
  self.s.affect._apply('default','announcement','announcement',{'curiosity':.01},'fixture',1,'user_message');p.write_text('c');self.s.affect.observe_environment({'test':str(p)});self.assertEqual(self.s.affect.history()['items'][0]['kind'],'anticipated_change')
 def test_only_verified_auto_source_eligible(self):
  self.event('你做得很好',source_msg_id='msg1');self.propose('warmth','你做得很好',{'joy':.1});self.s.affect.for_request({'mode':'explicit','query':'你做得很好','source_msg_id':'msg1'});self.s.affect.for_request({'mode':'auto','query':'别的原文','source_msg_id':'msg1'});self.s.affect.for_request({'mode':'auto','query':'','source_msg_id':'msg1'});self.assertEqual(self.f.calls,0);self.s.affect.for_request({'mode':'auto','query':'你做得很好','source_msg_id':'msg1'});self.assertEqual(len(self.s.affect.history()['items']),1)
 def test_affect_writer_and_reviewer_receive_owner_narration_rules(self):
  eid=self.event('今天我们一起完成了');self.propose('shared_success','一起完成了',{'joy':.08});self.s.affect.apply_event(eid)
  self.assertEqual(len(self.f.instructions),2)
  for instruction in self.f.instructions:
   self.assertIn('本人是阿岚，女性',instruction)
   self.assertIn('不用“用户／该用户／他／他的”称呼阿岚',instruction)
 def test_thirty_days_freeze_not_reset_weight_dust_and_restore(self):
  mid=self.s.upsert({'content':'记忆甲','strength':3})['id'];self.now+=30*DAY;self.assertEqual(self.s.retention.state(mid)['weight'],3);self.now+=15*DAY;self.assertEqual(self.s.retention.state(mid)['weight'],2.5);self.s.retention.touch([mid],'receipt');self.now+=30*DAY;self.assertEqual(self.s.retention.state(mid)['weight'],2.5);self.now+=30*DAY;self.assertEqual(self.s.retention.state(mid)['weight'],1.5);self.s.retention.touch([mid],'receipt');self.assertEqual(self.s.retention.state(mid)['weight'],1.5);self.now+=45*DAY;self.assertEqual(self.s.retention.sweep()['dusted'],1);self.assertEqual(self.s.get(mid)['version_status'],'dusted');self.assertEqual(self.s.get(mid)['content'],'记忆甲');self.s.retention.restore(mid);self.assertEqual(self.s.retention.state(mid)['weight'],1);self.assertEqual(self.s.get(mid)['version_status'],'current')
 def test_browse_does_not_protect_and_conflicting_restore_is_candidate(self):
  a=self.s.upsert({'content':'旧绿茶','fact_key':'tea','strength':1})['id'];self.now+=60*DAY;self.s.browse({});self.s.retention.sweep();self.s.upsert({'content':'新红茶','fact_key':'tea'});self.assertEqual(self.s.retention.restore(a)['status'],'candidate')
 def test_inbound_affect_job_is_durable(self):
  eid=self.event('刚刚发现了新工具')
  with self.s.connect() as db:r=db.execute("SELECT payload_json FROM memory_jobs WHERE kind='affect_event'").fetchone()
  self.assertEqual(json.loads(r[0])['id'],eid)
if __name__=='__main__':unittest.main()
