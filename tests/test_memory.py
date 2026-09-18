import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from memory_core import MemoryStore


class MemoryStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MemoryStore(os.path.join(self.tmp.name, "memory.db"), os.path.join(self.tmp.name, "archive"))

    def tearDown(self): self.tmp.cleanup()

    def test_dual_time_conflict_and_explicit_supersession(self):
        old = self.store.upsert({"content": "她喜欢喝热牛奶", "fact_key": "drink", "occurred_at": "2026-01-01T00:00:00Z", "known_at": "2026-01-02T00:00:00Z"})
        candidate = self.store.upsert({"content": "她现在不喝牛奶", "fact_key": "drink", "occurred_at": "2026-09-01T00:00:00Z"})
        self.assertEqual(candidate["status"], "conflict_review")
        self.assertEqual(len(self.store.list()), 1)
        newer = self.store.supersede(old["memory"]["id"], {"content": "她现在不喝牛奶"})
        self.assertEqual(newer["status"], "superseded")
        self.assertEqual(len(self.store.history("drink")), 3)
        self.assertEqual(len(self.store.list()), 1)

    def test_decay_emotion_and_hit_bump(self):
        ancient = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        low = self.store.upsert({"content": "海边散步", "fact_key": "a", "strength": 5, "strength_updated_at": ancient, "emotion_intensity": 0})["memory"]
        high = self.store.upsert({"content": "海边散步很重要", "fact_key": "b", "strength": 3, "emotion_intensity": 5})["memory"]
        recalled = self.store.recall("海边散步", limit=2)
        self.assertEqual(recalled[0]["id"], high["id"])
        self.assertGreater(self.store.get(high["id"])["recall_count"], 0)
        self.assertLess(recalled[1]["effective_strength"], low["strength"])

    def test_raw_neighbors_and_patrol_never_delete(self):
        events = [self.store.ingest_event({"session_id": "s", "sequence_no": i, "role": "user" if i % 2 == 0 else "assistant", "content": f"上下文{i}"}) for i in range(5)]
        mem = self.store.upsert({"content": "上下文2 很关键", "source_event_id": events[2]["id"]})["memory"]
        hit = self.store.recall("上下文2")[0]
        self.assertEqual(len(hit["raw_neighbors"]), 5)
        before = len(self.store.list(include_history=True))
        report = self.store.patrol()
        self.assertEqual(report["deleted"], 0)
        self.assertEqual(before, len(self.store.list(include_history=True)))


if __name__ == "__main__": unittest.main()

