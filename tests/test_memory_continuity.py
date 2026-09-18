import tempfile
import unittest

from memory_core import MemoryStore as LegacyStore
from memory_v2 import MemoryStore
from memory_worker import Worker
from test_memory_v2 import Models


class ContinuityModels(Models):
    fail_continuity=False
    contradict_approval=False
    def json(self, instruction, data, **kwargs):
        if self.fail_continuity and ("连续性候选核对员" in instruction or "连续性副脑" in instruction):raise RuntimeError("continuity_model_failed")
        if "连续性候选核对员" in instruction:
            return {"approved":[{"kind":x["kind"],"index":x["source_index"]} for x in data["candidates"]]}, {}
        if "潜在便签审批员" in instruction:
            approved=[x["index"] for x in data["latents"]]
            return {"approved_indices":approved,"rejections":[{"index":approved[0],"reason":"conflict"}] if self.contradict_approval and approved else []}, {}
        if "连续性副脑" in instruction:
            event=data["events"][-1]
            evidence=[{"event_id":event["id"],"quote":event["content"]}]
            return {
                "trajectories":[{"axis_key":"continuity-test","title":"还没走完","summary":"仍在比较连续性方案","open_question":"哪层先接入？","evidence":evidence}],
                "nearfield":[{"body":"这几天正在比较连续性方案","evidence":evidence}],
                "latents":[{"text":"那条没走完的线还停在这里。","evidence":evidence}],
            }, {}
        return super().json(instruction,data,**kwargs)


class TestContinuity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=MemoryStore(self.tmp.name+"/db",self.tmp.name+"/archive",ContinuityModels())

    def tearDown(self):self.tmp.cleanup()

    def event(self, text="这几天在比较连续性方案"):
        return self.s.ingest_event({"namespace":"n","session_id":"s","role":"user","content":text,"source_msg_id":"m1"})["id"]

    def evidence(self, eid, quote="这几天在比较连续性方案"):
        return [{"event_id":eid,"quote":quote}]

    def test_sidecar_does_not_change_fact_recall_or_indexes(self):
        mid=self.s.upsert({"namespace":"n","content":"喜欢绿茶"})["id"]
        before=self.s.recall_pack({"namespace":"n","query":"绿茶","budget_tokens":200})
        eid=self.event();self.s.continuity.add_trajectory({"namespace":"n","axis_key":"a","title":"方案","summary":"还没走完","evidence":self.evidence(eid)})
        after=self.s.recall_pack({"namespace":"n","query":"绿茶","budget_tokens":200})
        self.assertEqual([x["id"] for x in before["memories"]],[mid]);self.assertEqual([x["id"] for x in after["memories"]],[mid])
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM memory_fts").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM memories").fetchone()[0],1)

    def test_evidence_is_exact_namespace_scoped_and_deduplicated(self):
        eid=self.event();data={"namespace":"n","axis_key":"a","title":"方案","summary":"还没走完","evidence":self.evidence(eid)}
        self.assertEqual(self.s.continuity.add_trajectory(data)["status"],"created")
        self.assertEqual(self.s.continuity.add_trajectory(data)["status"],"existing")
        trajectory_id=self.s.continuity.list("trajectory","n")[0]["id"]
        with self.assertRaises(KeyError):self.s.continuity.set_trajectory_state(trajectory_id,"resolved","other")
        self.assertEqual(self.s.continuity.set_trajectory_state(trajectory_id,"paused","n")["state"],"paused")
        self.s.continuity.add_trajectory(data)
        self.assertEqual(self.s.continuity.list("trajectory","n")[0]["state"],"paused")
        with self.assertRaises(ValueError):self.s.continuity.add_latent({"namespace":"n","text":"错误","evidence":self.evidence(eid,"伪造引文")})
        with self.assertRaises(ValueError):self.s.continuity.add_nearfield({"namespace":"other","body":"越界","evidence":self.evidence(eid)})

    def test_nearfield_expires_and_latent_requires_review(self):
        eid=self.event();nf=self.s.continuity.add_nearfield({"namespace":"n","body":"近期上下文","evidence":self.evidence(eid)})
        latent=self.s.continuity.add_latent({"namespace":"n","text":"一个联想","evidence":self.evidence(eid)})
        self.assertEqual(self.s.continuity.list("latent","n","approved"),[])
        with self.assertRaises(KeyError):self.s.continuity.review_latent(latent["id"],"approve",namespace="other")
        self.assertEqual(self.s.continuity.review_latent(latent["id"],"approve",namespace="n")["status"],"approved")
        self.assertEqual(len(self.s.continuity.list("latent","n","approved")),1)
        with self.s.connect() as db:db.execute("UPDATE continuity_latent_notes SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",(latent["id"],))
        self.assertEqual(self.s.continuity.list("latent","n","approved"),[])
        self.assertNotIn("latent",{x["kind"] for x in self.s.continuity.pack({"namespace":"n","query":"一个联想"})["items"]})
        with self.s.connect() as db:db.execute("UPDATE continuity_nearfield_snapshots SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",(nf["id"],))
        self.assertEqual(self.s.continuity.list("nearfield","n"),[])

    def test_pack_has_independent_budget_and_commit_dedupe(self):
        eid=self.event();self.s.continuity.add_trajectory({"namespace":"n","axis_key":"a","title":"连续性方案","summary":"还没走完","open_question":"先做哪层","evidence":self.evidence(eid)})
        result=self.s.continuity.pack({"namespace":"n","query":"连续性方案","session_key":"sess","budget_tokens":180})
        self.assertLessEqual(result["estimated_tokens"],180);self.assertTrue(result["historical_derived"]);self.assertTrue(result["items"])
        self.s.continuity.commit(result["continuity_recall_id"])
        self.assertFalse(self.s.continuity.pack({"namespace":"n","query":"连续性方案","session_key":"sess","budget_tokens":180})["items"])

    def test_worker_creates_grounded_layers_and_model_approves_latent(self):
        eid=self.event();result=Worker(self.s).continuity_refresh({"ids":[eid],"focus_ids":[eid]})
        self.assertEqual(result["created"],{"trajectory":1,"nearfield":1,"latent":1})
        self.assertEqual(len(self.s.continuity.list("trajectory","n","open",include_evidence=True)),1)
        self.assertEqual(len(self.s.continuity.list("nearfield","n",include_evidence=True)),1)
        self.assertEqual(result["model_approved_latents"],1)
        self.assertEqual(len(self.s.continuity.list("latent","n","approved",include_evidence=True)),1)
        packed={item["kind"] for item in self.s.continuity.pack({"namespace":"n","query":"那条没走完的线"})["items"]}
        self.assertIn("trajectory",packed);self.assertIn("latent",packed)

    def test_worker_failure_writes_no_continuity_and_synthetic_is_filtered(self):
        eid=self.event();self.s.models.fail_continuity=True
        with self.assertRaises(RuntimeError):Worker(self.s).continuity_refresh({"ids":[eid],"focus_ids":[eid]})
        self.assertEqual(self.s.continuity.status("n")["trajectory"]["total"],0)
        synthetic=self.s.ingest_event({"namespace":"n","session_id":"s2","role":"user","content":"[worker] 后台任务完成","source_msg_id":"m2"})["id"]
        self.s.models.fail_continuity=False
        self.assertEqual(Worker(self.s).continuity_refresh({"ids":[synthetic],"focus_ids":[synthetic]})["skipped"],"no_user_evidence")

    def test_latent_rejection_wins_over_conflicting_approval(self):
        eid=self.event();self.s.models.contradict_approval=True
        result=Worker(self.s).continuity_refresh({"ids":[eid],"focus_ids":[eid]})
        self.assertEqual(result["model_approved_latents"],0)
        self.assertEqual(len(self.s.continuity.list("latent","n","review_required")),1)

    def test_scheduler_batches_only_new_events_for_continuity(self):
        eid=self.event();other=self.s.ingest_event({"namespace":"other","session_id":"s","role":"user","content":"另一个空间的内容","source_msg_id":"other-m1"})["id"];Worker(self.s).schedule()
        with self.s.connect() as db:
            rows=db.execute("SELECT payload_json FROM memory_jobs WHERE kind='continuity_refresh'").fetchall()
        self.assertEqual(len(rows),2)
        payloads=[__import__('json').loads(x[0]) for x in rows]
        self.assertEqual({x['namespace'] for x in payloads},{'n','other'})
        self.assertTrue(all(not ({eid,other}<=set(x['ids'])) for x in payloads))
        with self.assertRaises(ValueError):Worker(self.s).continuity_refresh({'ids':[eid,other]})

    def test_first_migration_does_not_backfill_old_event_history(self):
        with tempfile.TemporaryDirectory() as root:
            legacy=LegacyStore(root+"/db",root+"/archive")
            legacy.ingest_event({"namespace":"n","session_id":"old","role":"user","content":"很久以前的历史"})
            upgraded=MemoryStore(root+"/db",root+"/archive",ContinuityModels());Worker(upgraded).schedule()
            with upgraded.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM memory_jobs WHERE kind='continuity_refresh'").fetchone()[0],0)


if __name__ == "__main__":unittest.main()
