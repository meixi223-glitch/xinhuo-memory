import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from situation_frames import SituationFrameStore


class SituationFrameStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SituationFrameStore(os.path.join(self.tmp.name, "memory.sqlite3"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_read_latest_fresh_frame(self):
        generated = datetime.now(timezone.utc)
        written = self.store.write({
            "frame_id": "f1", "generated_at": generated.isoformat(), "focus": "ship phase one",
            "phase": "implementation", "transition": "inventory to code", "action": "test",
            "body_state": "steady", "relation_posture": "collaborative",
            "action_impulse": "finish safely", "evidence_event_ids": ["e1", "e2"], "ttl_seconds": 60,
        })
        self.assertFalse(written["stale"])
        latest = self.store.latest(generated + timedelta(seconds=59))
        self.assertEqual(latest["frame_id"], "f1")
        self.assertEqual(latest["evidence_event_ids"], ["e1", "e2"])
        self.assertFalse(latest["stale"])

    def test_expired_latest_is_returned_with_stale_true(self):
        generated = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)
        self.store.write({"generated_at": generated.isoformat(), "focus": "old", "ttl_seconds": 10})
        latest = self.store.latest(generated + timedelta(seconds=10))
        self.assertTrue(latest["stale"])
        self.assertIsNone(self.store.latest_unexpired(generated + timedelta(seconds=10)))

    def test_requires_positive_ttl_and_string_evidence_ids(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            self.store.write({"focus": "bad", "ttl_seconds": 0})
        with self.assertRaisesRegex(ValueError, "array of strings"):
            self.store.write({"focus": "bad", "ttl_seconds": 60, "evidence_event_ids": [1]})


if __name__ == "__main__":
    unittest.main()
