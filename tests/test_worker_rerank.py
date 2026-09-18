import unittest
from memory_worker import Worker
class Ranker:
 def __init__(self):self.calls=[]
 def rerank(self,q,docs,top_n=2):
  self.calls.append((q,docs,top_n));return [{'index':2,'score':.91},{'index':0,'score':.72}],{'input_tokens':70}
class S:pass
class TestWorkerRerank(unittest.TestCase):
 def test_independent_reranker_reorders_cosine_neighbors_before_relation_review(self):
  s=S();s.models=Ranker();nearby=[(.9,{'id':'a','content':'相似主题'}),(.8,{'id':'b','content':'无关时间'}),(.7,{'id':'c','content':'同一件事的直接记录'})];ranked,usage,error=Worker(s).rank_neighbors({'content':'当前事实'},nearby)
  self.assertEqual([x['id'] for _,x in ranked],['c','a']);self.assertEqual(s.models.calls[0][0],'当前事实');self.assertEqual(usage['input_tokens'],70);self.assertIsNone(error)
 def test_reranker_outage_is_visible_and_does_not_delete_any_memory(self):
  s=S();s.models=Ranker();s.models.rerank=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError())
  result,usage,error=Worker(s).rank_neighbors({'content':'事实'},[(.8,{'id':'a','content':'候选'})]);self.assertEqual(result[0][1]['id'],'a');self.assertEqual(error,'rerank:RuntimeError')
if __name__=='__main__':unittest.main()
