import tempfile,unittest
from memory_v2 import MemoryStore
from test_memory_v2 import Models
class TestLinkRecall(unittest.TestCase):
 def test_shared_person_is_not_semantic_evidence_but_verified_relation_expands(self):
  with tempfile.TemporaryDirectory() as root:
   s=MemoryStore(root+'/db',root+'/arc',Models());a=s.upsert({'content':'雨伞放门口了'})['id'];b=s.upsert({'content':'猫咪在吃饭'})['id']
   with s.connect() as db:db.execute('INSERT INTO memory_links VALUES(?,?,?,?,?)',(a,b,'shared_entity',.8,'entity_index'))
   rows,_=s._candidates('雨伞','default');self.assertEqual({r['id'] for r in rows},{a})
   with s.connect() as db:db.execute('INSERT INTO memory_links VALUES(?,?,?,?,?)',(a,b,'same_event',.9,'worker_verified'))
   rows,_=s._candidates('雨伞','default');self.assertEqual({r['id'] for r in rows},{a,b});self.assertEqual(s.get(a)['links'][0]['relation'],'same_event')
if __name__=='__main__':unittest.main()
