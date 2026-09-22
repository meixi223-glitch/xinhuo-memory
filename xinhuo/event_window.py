#!/usr/bin/env python3
"""Compatibility event layer for channel-aware, deduplicated window reads."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
import uuid
from datetime import datetime, timezone
from typing import Any


def utc_iso(value: str | None = None, assume_naive_utc: bool = False) -> str:
    if not value:
        dt = datetime.now(timezone.utc)
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            if not assume_naive_utc:
                raise ValueError("timestamp must include a timezone")
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def dedup_hash(role: str, content: str, attachment_ref: str | None = None) -> str:
    normalized = " ".join(content.split()).strip().casefold()
    material = f"{role.strip().casefold()}\0{normalized}\0{attachment_ref or ''}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class EventWindowStore:
    FIELDS = {
        "event_id": "TEXT",
        "occurred_at_utc": "TEXT",
        "channel": "TEXT NOT NULL DEFAULT 'unknown'",
        "role": "TEXT NOT NULL DEFAULT 'unknown'",
        "content": "TEXT NOT NULL DEFAULT ''",
        "attachment_ref": "TEXT",
        "dedup_hash": "TEXT",
        "channel_private": "INTEGER NOT NULL DEFAULT 0",
        "privacy_label": "TEXT NOT NULL DEFAULT 'standard'",
        "namespace": "TEXT NOT NULL DEFAULT 'default'",
        "source_raw_event_id": "TEXT",
        "created_at_utc": "TEXT",
    }

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.migrate()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally:
            db.close()

    def migrate(self) -> None:
        with self.connect() as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'"
            ).fetchone()
            if not exists:
                db.execute("""
                    CREATE TABLE events (
                      event_id TEXT PRIMARY KEY,
                      occurred_at_utc TEXT NOT NULL,
                      channel TEXT NOT NULL DEFAULT 'unknown',
                      role TEXT NOT NULL,
                      content TEXT NOT NULL,
                      attachment_ref TEXT,
                      dedup_hash TEXT NOT NULL,
                      channel_private INTEGER NOT NULL DEFAULT 0,
                      privacy_label TEXT NOT NULL DEFAULT 'standard',
                      namespace TEXT NOT NULL DEFAULT 'default',
                      source_raw_event_id TEXT,
                      created_at_utc TEXT NOT NULL
                    )
                """)
            else:
                columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
                for name, declaration in self.FIELDS.items():
                    if name not in columns:
                        db.execute(f"ALTER TABLE events ADD COLUMN {name} {declaration}")

            now = utc_iso()
            columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            if "id" in columns:
                db.execute("UPDATE events SET event_id=COALESCE(NULLIF(event_id,''),id) WHERE event_id IS NULL OR event_id='' ")
            db.execute(
                "UPDATE events SET event_id='evt_legacy_'||lower(hex(randomblob(16))) WHERE event_id IS NULL OR event_id=''"
            )
            if "occurred_at" in columns:
                db.execute("UPDATE events SET occurred_at_utc=occurred_at WHERE occurred_at_utc IS NULL OR occurred_at_utc='' ")
            db.execute("UPDATE events SET occurred_at_utc=? WHERE occurred_at_utc IS NULL OR occurred_at_utc=''", (now,))
            db.execute("UPDATE events SET created_at_utc=? WHERE created_at_utc IS NULL OR created_at_utc=''", (now,))
            for row in db.execute("SELECT rowid,occurred_at_utc,created_at_utc FROM events"):
                db.execute(
                    "UPDATE events SET occurred_at_utc=?,created_at_utc=? WHERE rowid=?",
                    (utc_iso(str(row[1]), True), utc_iso(str(row[2]), True), row[0]),
                )
            for row in db.execute("SELECT rowid,role,content,attachment_ref FROM events WHERE dedup_hash IS NULL OR dedup_hash='' "):
                db.execute(
                    "UPDATE events SET dedup_hash=? WHERE rowid=?",
                    (dedup_hash(str(row[1] or "unknown"), str(row[2] or ""), row[3]), row[0]),
                )

            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_id ON events(event_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_events_window ON events(occurred_at_utc,channel)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_events_dedup ON events(dedup_hash)")
            db.execute("DROP INDEX IF EXISTS idx_events_raw_source")
            db.execute("CREATE INDEX IF NOT EXISTS idx_events_raw_source_lookup ON events(source_raw_event_id)")
            self._backfill_raw_events(db)

    def _backfill_raw_events(self, db: sqlite3.Connection) -> None:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='raw_events'").fetchone():
            return
        now = utc_iso()
        rows = db.execute(
            "SELECT id,namespace,role,content,occurred_at,created_at FROM raw_events ORDER BY occurred_at,id"
        ).fetchall()
        for row in rows:
            role, content = str(row[2]), str(row[3])
            db.execute(
                """INSERT OR IGNORE INTO events(
                     event_id,occurred_at_utc,channel,role,content,attachment_ref,dedup_hash,
                     channel_private,privacy_label,namespace,source_raw_event_id,created_at_utc
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(row[0]), utc_iso(str(row[4]), True), "unknown", role, content, None,
                    dedup_hash(role, content), 0, "standard", str(row[1] or "default"),
                    str(row[0]), utc_iso(str(row[5] or now), True),
                ),
            )

    def ingest(self, data: dict[str, Any], source_raw_event_id: str | None = None) -> dict[str, Any]:
        content = str(data.get("content") or "").strip()
        if not content:
            raise ValueError("content is required")
        role = str(data.get("role") or "user").strip() or "user"
        attachment = str(data.get("attachment_ref") or "").strip() or None
        event_id = str(data.get("event_id") or data.get("id") or source_raw_event_id or f"evt_{uuid.uuid4().hex}")
        occurred = utc_iso(str(data.get("occurred_at") or data.get("occurred_at_utc") or "") or None)
        supplied_hash = str(data.get("dedup_hash") or "").strip()
        digest = supplied_hash or dedup_hash(role, content, attachment)
        with self.connect() as db:
            db.execute(
                """INSERT INTO events(
                     event_id,occurred_at_utc,channel,role,content,attachment_ref,dedup_hash,
                     channel_private,privacy_label,namespace,source_raw_event_id,created_at_utc
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(event_id) DO UPDATE SET
                     occurred_at_utc=excluded.occurred_at_utc,channel=excluded.channel,
                     role=excluded.role,content=excluded.content,attachment_ref=excluded.attachment_ref,
                     dedup_hash=excluded.dedup_hash,channel_private=excluded.channel_private,
                     privacy_label=excluded.privacy_label""",
                (
                    event_id, occurred, str(data.get("channel") or "unknown"), role, content,
                    attachment, digest, int(bool(data.get("channel_private", data.get("private", False)))),
                    str(data.get("privacy_label") or "standard"), str(data.get("namespace") or "default"),
                    source_raw_event_id, utc_iso(),
                ),
            )
            row = db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        return self._event(row)

    @staticmethod
    def _event(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["channel_private"] = bool(value["channel_private"])
        return value

    def window(self, from_utc: str, to_utc: str, channel: str | None = None) -> dict[str, Any]:
        start, end = utc_iso(from_utc), utc_iso(to_utc)
        if start > end:
            raise ValueError("from must be before or equal to to")
        sql = "SELECT * FROM events WHERE occurred_at_utc>=? AND occurred_at_utc<=?"
        params: list[Any] = [start, end]
        if channel:
            sql += " AND channel=?"
            params.append(channel)
        sql += " ORDER BY occurred_at_utc,event_id"
        with self.connect() as db:
            rows = db.execute(sql, params).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            event = self._event(row)
            key = event["dedup_hash"]
            if key not in grouped:
                event["channels"] = [event["channel"]]
                grouped[key] = event
            else:
                current = grouped[key]
                if event["channel"] not in current["channels"]:
                    current["channels"].append(event["channel"])
                current["channel_private"] = bool(current["channel_private"] or event["channel_private"])
                if current["privacy_label"] == "standard" and event["privacy_label"] != "standard":
                    current["privacy_label"] = event["privacy_label"]
        events = list(grouped.values())
        return {"events": events, "count": len(events), "matched_rows": len(rows), "deduplicated": len(rows) - len(events)}
