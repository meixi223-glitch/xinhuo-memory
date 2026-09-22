import os
import sqlite3
import tempfile
import unittest

from event_window import EventWindowStore


class EventWindowStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "memory.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_migrates_raw_events_without_changing_old_table(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("""CREATE TABLE raw_events(
                id TEXT PRIMARY KEY, namespace TEXT, session_id TEXT, sequence_no INTEGER,
                role TEXT, content TEXT, occurred_at TEXT, known_at TEXT,
                content_hash TEXT UNIQUE, created_at TEXT)""")
            db.execute(
                "INSERT INTO raw_events VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("raw-1", "default", "s", 0, "user", "hello", "2026-09-22T00:00:00", "2026-09-22T00:00:00", "legacy-hash", "2026-09-22T00:00:00"),
            )
        store = EventWindowStore(self.db_path)
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0], 1)
            row = db.execute("SELECT event_id,channel,source_raw_event_id,occurred_at_utc FROM events").fetchone()
        self.assertEqual(row, ("raw-1", "unknown", "raw-1", "2026-09-22T00:00:00.000Z"))

    def test_window_filters_channel_and_deduplicates_across_channels(self):
        store = EventWindowStore(self.db_path)
        base = {"role": "user", "content": "Same message", "occurred_at": "2026-09-22T01:00:00Z"}
        store.ingest({**base, "event_id": "e1", "channel": "wecom", "channel_private": True})
        store.ingest({**base, "event_id": "e2", "channel": "forum", "occurred_at": "2026-09-22T01:01:00Z"})
        store.ingest({**base, "event_id": "e3", "channel": "valley", "content": "different", "occurred_at": "2026-09-22T01:02:00Z"})
        result = store.window("2026-09-22T00:00:00Z", "2026-09-22T02:00:00Z")
        self.assertEqual(result["matched_rows"], 3)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["deduplicated"], 1)
        same = result["events"][0]
        self.assertEqual(same["channels"], ["wecom", "forum"])
        self.assertTrue(same["channel_private"])
        filtered = store.window("2026-09-22T00:00:00Z", "2026-09-22T02:00:00Z", "forum")
        self.assertEqual(filtered["count"], 1)
        self.assertEqual(filtered["events"][0]["channel"], "forum")

    def test_adds_missing_columns_to_legacy_events_table(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("CREATE TABLE events(id TEXT PRIMARY KEY, occurred_at TEXT, role TEXT, content TEXT)")
            db.execute("INSERT INTO events VALUES('old-1','2026-09-22T00:00:00Z','assistant','legacy')")
        EventWindowStore(self.db_path)
        with sqlite3.connect(self.db_path) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            row = db.execute("SELECT event_id,dedup_hash,channel_private FROM events").fetchone()
        self.assertTrue({"event_id", "occurred_at_utc", "channel", "attachment_ref", "dedup_hash", "channel_private"} <= columns)
        self.assertEqual(row[0], "old-1")
        self.assertEqual(len(row[1]), 64)
        self.assertEqual(row[2], 0)


if __name__ == "__main__":
    unittest.main()
