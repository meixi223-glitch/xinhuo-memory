#!/usr/bin/env python3
"""Small, auditable local memory store inspired by Graphiti/OmniMemory/LMC-5."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def structured_payload(value: Any) -> dict:
    """MCP structuredContent must be a JSON object, never a top-level array."""
    return value if isinstance(value, dict) else {"data": value}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def terms(text: str) -> set[str]:
    clean = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    latin = set(re.findall(r"[a-z0-9_\-]{2,}", clean))
    han_runs = re.findall(r"[\u3400-\u9fff]+", clean)
    han: set[str] = set()
    for run in han_runs:
        han.update(run)
        han.update(run[i : i + 2] for i in range(len(run) - 1))
    return latin | han


def lexical_score(query: str, content: str) -> float:
    q, c = terms(query), terms(content)
    if not q or not c:
        return 0.0
    overlap = len(q & c) / math.sqrt(len(q) * len(c))
    phrase = 0.35 if len(query.strip()) >= 2 and query.lower() in content.lower() else 0.0
    return min(1.0, overlap + phrase)


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  namespace TEXT NOT NULL DEFAULT 'default',
  kind TEXT NOT NULL DEFAULT 'fact',
  content TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  fact_key TEXT,
  occurred_at TEXT NOT NULL,
  known_at TEXT NOT NULL,
  superseded_at TEXT,
  supersedes_id TEXT,
  superseded_by_id TEXT,
  version_status TEXT NOT NULL DEFAULT 'current',
  strength REAL NOT NULL DEFAULT 3,
  strength_updated_at TEXT NOT NULL,
  importance REAL NOT NULL DEFAULT 3,
  confidence REAL NOT NULL DEFAULT 0.7,
  emotion_label TEXT,
  emotion_intensity INTEGER NOT NULL DEFAULT 0,
  pinned INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'bridge',
  source_ref TEXT,
  source_event_id TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  response_tendency TEXT,
  last_recalled_at TEXT,
  recall_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  FOREIGN KEY(supersedes_id) REFERENCES memories(id),
  FOREIGN KEY(superseded_by_id) REFERENCES memories(id)
);
CREATE INDEX IF NOT EXISTS idx_mem_current ON memories(namespace, version_status, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_mem_fact ON memories(namespace, fact_key, version_status);
CREATE TABLE IF NOT EXISTS raw_events (
  id TEXT PRIMARY KEY,
  namespace TEXT NOT NULL DEFAULT 'default',
  session_id TEXT,
  sequence_no INTEGER NOT NULL DEFAULT 0,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  known_at TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON raw_events(namespace, session_id, sequence_no);
CREATE TABLE IF NOT EXISTS conflict_reviews (
  id TEXT PRIMARY KEY,
  namespace TEXT NOT NULL,
  fact_key TEXT NOT NULL,
  existing_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  memory_id TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS glossary (
  term TEXT PRIMARY KEY,
  definition TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS thoughts (
  id TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  created_at TEXT,
  mood TEXT,
  status TEXT DEFAULT 'open',
  resolved_at TEXT
);
"""


class MemoryStore:
    def __init__(self, db_path: str, archive_dir: str):
        self.db_path = db_path
        self.archive_dir = Path(archive_dir)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["tags"] = json.loads(value.pop("tags_json", "[]") or "[]")
        value["pinned"] = bool(value.get("pinned"))
        return value

    @staticmethod
    def _effective_strength(row: dict[str, Any], at: datetime | None = None) -> float:
        at = at or datetime.now(timezone.utc)
        updated = parse_time(row.get("strength_updated_at"))
        days = max(0.0, (at - updated).total_seconds() / 86400)
        half_life = 120.0 if row.get("pinned") else 45.0
        return 1.0 + (float(row.get("strength", 3)) - 1.0) * math.exp(-math.log(2) * days / half_life)

    def _audit(self, db: sqlite3.Connection, action: str, memory_id: str | None, details: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO audit_log(action,memory_id,details_json,created_at) VALUES(?,?,?,?)",
            (action, memory_id, json.dumps(details, ensure_ascii=False), now_iso()),
        )

    def append_archive(self, event: dict[str, Any]) -> None:
        month = now_iso()[:7]
        target = self.archive_dir / f"memory-{month}.jsonl"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"archivedAt": now_iso(), **event}, ensure_ascii=False) + "\n")
        os.chmod(target, 0o600)

    def ingest_event(self, data: dict[str, Any]) -> dict[str, Any]:
        content = str(data.get("content") or "").strip()
        if not content:
            raise ValueError("content is required")
        namespace = str(data.get("namespace") or "default")
        session_id = str(data.get("session_id") or "") or None
        role = str(data.get("role") or "user")
        occurred = str(data.get("occurred_at") or now_iso())
        known = str(data.get("known_at") or now_iso())
        digest = hashlib.sha256(f"{namespace}\0{session_id}\0{role}\0{content}".encode()).hexdigest()
        event_id = str(data.get("id") or f"evt_{uuid.uuid4().hex}")
        with self.connect() as db:
            if data.get("sequence_no") is None:
                seq = db.execute(
                    "SELECT COALESCE(MAX(sequence_no),-1)+1 FROM raw_events WHERE namespace=? AND session_id IS ?",
                    (namespace, session_id),
                ).fetchone()[0]
            else:
                seq = int(data["sequence_no"])
            db.execute(
                "INSERT OR IGNORE INTO raw_events VALUES(?,?,?,?,?,?,?,?,?,?)",
                (event_id, namespace, session_id, seq, role, content, occurred, known, digest, now_iso()),
            )
            row = db.execute("SELECT * FROM raw_events WHERE content_hash=?", (digest,)).fetchone()
        self.append_archive({"type": "raw_event", "event": dict(row)})
        return dict(row)

    def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        content = str(data.get("content") or data.get("text") or "").strip()
        if not content:
            raise ValueError("content is required")
        namespace = str(data.get("namespace") or "default")
        fact_key = str(data.get("fact_key") or "").strip() or None
        ts = now_iso()
        digest = hashlib.sha256(content.encode()).hexdigest()
        with self.connect() as db:
            same = db.execute(
                "SELECT * FROM memories WHERE namespace=? AND content_hash=? AND version_status='current' LIMIT 1",
                (namespace, digest),
            ).fetchone()
            if same:
                new_strength = min(5.0, float(same["strength"]) + 0.2)
                db.execute(
                    "UPDATE memories SET strength=?,strength_updated_at=?,updated_at=? WHERE id=?",
                    (new_strength, ts, ts, same["id"]),
                )
                self._audit(db, "seen_again", same["id"], {})
                return {"status": "existing", "memory": self._row(db.execute("SELECT * FROM memories WHERE id=?", (same["id"],)).fetchone())}

            memory_id = str(data.get("id") or f"mem_{uuid.uuid4().hex}")
            occurred = str(data.get("occurred_at") or data.get("valid_as_of") or ts)
            known = str(data.get("known_at") or data.get("created_at") or ts)
            strength = clamp(data.get("strength"), 1, 5, 3)
            importance = clamp(data.get("importance"), 1, 5, 3)
            confidence = clamp(data.get("confidence"), 0, 1, 0.7)
            emotion_intensity = int(clamp(data.get("emotion_intensity"), 0, 5, 0))
            current = None
            if fact_key:
                current = db.execute(
                    "SELECT * FROM memories WHERE namespace=? AND fact_key=? AND version_status='current' ORDER BY known_at DESC LIMIT 1",
                    (namespace, fact_key),
                ).fetchone()
            status = str(data.get("version_status") or ("candidate" if current else "current"))
            fields = (
                memory_id, namespace, str(data.get("kind") or data.get("type") or "fact"), content,
                str(data.get("summary") or ""), fact_key, occurred, known,
                data.get("superseded_at"), data.get("supersedes_id"), data.get("superseded_by_id"), status,
                strength, str(data.get("strength_updated_at") or known), importance, confidence,
                data.get("emotion_label"), emotion_intensity, int(bool(data.get("pinned"))),
                str(data.get("source") or "bridge"), data.get("source_ref"), data.get("source_event_id"),
                json.dumps(data.get("tags") or [], ensure_ascii=False), data.get("response_tendency"),
                data.get("last_recalled_at"), int(data.get("recall_count") or 0),
                str(data.get("created_at") or known), str(data.get("updated_at") or ts), digest,
            )
            db.execute("INSERT INTO memories VALUES(" + ",".join("?" for _ in fields) + ")", fields)
            result_status = "created"
            if current and status == "candidate":
                review_id = f"conf_{uuid.uuid4().hex}"
                db.execute(
                    "INSERT INTO conflict_reviews VALUES(?,?,?,?,?,'open',?,?,NULL)",
                    (review_id, namespace, fact_key, current["id"], memory_id, "same fact_key with changed content", ts),
                )
                result_status = "conflict_review"
            self._audit(db, result_status, memory_id, {"fact_key": fact_key})
            row = db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        self.append_archive({"type": "memory_write", "status": result_status, "memory": self._row(row)})
        return {"status": result_status, "memory": self._row(row)}

    def supersede(self, old_id: str, new_data: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as db:
            old = db.execute("SELECT * FROM memories WHERE id=?", (old_id,)).fetchone()
        if not old:
            raise KeyError("old memory not found")
        payload = {**new_data, "namespace": new_data.get("namespace") or old["namespace"], "fact_key": new_data.get("fact_key") or old["fact_key"], "supersedes_id": old_id, "version_status": "current"}
        created = self.upsert(payload)
        new_id = created["memory"]["id"]
        ts = now_iso()
        with self.connect() as db:
            db.execute("UPDATE memories SET version_status='superseded',superseded_at=?,superseded_by_id=?,updated_at=? WHERE id=?", (ts, new_id, ts, old_id))
            db.execute("UPDATE conflict_reviews SET status='superseded',resolved_at=? WHERE candidate_id=? OR existing_id=?", (ts, new_id, old_id))
            self._audit(db, "supersede", new_id, {"old_id": old_id})
        return {"status": "superseded", "old_id": old_id, "memory": self.get(new_id)}

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, namespace: str = "default", include_history: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        sql = "SELECT * FROM memories WHERE namespace=?"
        args: list[Any] = [namespace]
        if not include_history:
            sql += " AND version_status='current'"
        sql += " ORDER BY pinned DESC, occurred_at DESC LIMIT ?"
        args.append(max(1, min(500, int(limit))))
        with self.connect() as db:
            return [self._row(row) for row in db.execute(sql, args)]

    def history(self, fact_key: str, namespace: str = "default") -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM memories WHERE namespace=? AND fact_key=? ORDER BY occurred_at,known_at", (namespace, fact_key))
            return [self._row(row) for row in rows]

    def _neighbors(self, event_id: str | None, radius: int = 2) -> list[dict[str, Any]]:
        if not event_id:
            return []
        with self.connect() as db:
            event = db.execute("SELECT * FROM raw_events WHERE id=?", (event_id,)).fetchone()
            if not event:
                return []
            rows = db.execute(
                "SELECT id,role,content,occurred_at,sequence_no FROM raw_events WHERE namespace=? AND session_id IS ? AND sequence_no BETWEEN ? AND ? ORDER BY sequence_no",
                (event["namespace"], event["session_id"], event["sequence_no"] - radius, event["sequence_no"] + radius),
            )
            return [dict(row) for row in rows]

    def recall(self, query: str, namespace: str = "default", limit: int = 8, include_history: bool = False, bump: bool = True) -> list[dict[str, Any]]:
        candidates = self.list(namespace, include_history, 500)
        at = datetime.now(timezone.utc)
        ranked: list[dict[str, Any]] = []
        for row in candidates:
            relevance = lexical_score(query, f"{row['content']} {row['summary']} {' '.join(row['tags'])}")
            if relevance <= 0 and not row["pinned"]:
                continue
            effective = self._effective_strength(row, at)
            age_days = max(0.0, (at - parse_time(row["occurred_at"])).total_seconds() / 86400)
            recency = math.exp(-age_days / 180.0)
            score = (0.58 * relevance + 0.16 * effective / 5 + 0.11 * float(row["importance"]) / 5 + 0.08 * row["emotion_intensity"] / 5 + 0.07 * recency)
            if row["pinned"]:
                score += 0.2
            row["effective_strength"] = round(effective, 4)
            row["score"] = round(score, 6)
            row["raw_neighbors"] = self._neighbors(row.get("source_event_id"))
            ranked.append(row)
        result = sorted(ranked, key=lambda item: item["score"], reverse=True)[: max(1, min(50, int(limit)))]
        if bump and result:
            ts = now_iso()
            with self.connect() as db:
                for row in result:
                    bumped = min(5.0, row["effective_strength"] + 0.25)
                    db.execute("UPDATE memories SET strength=?,strength_updated_at=?,last_recalled_at=?,recall_count=recall_count+1 WHERE id=?", (bumped, ts, ts, row["id"]))
                    self._audit(db, "recall_hit", row["id"], {"query_hash": hashlib.sha256(query.encode()).hexdigest()})
        return result

    def pin(self, memory_id: str, pinned: bool = True) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("UPDATE memories SET pinned=?,updated_at=? WHERE id=?", (int(pinned), now_iso(), memory_id))
            self._audit(db, "pin" if pinned else "unpin", memory_id, {})
        value = self.get(memory_id)
        if not value:
            raise KeyError("memory not found")
        return value

    def archive(self, memory_id: str, reason: str = "manual") -> dict[str, Any]:
        value = self.get(memory_id)
        if not value:
            raise KeyError("memory not found")
        ts = now_iso()
        with self.connect() as db:
            db.execute("UPDATE memories SET version_status='archived',updated_at=? WHERE id=?", (ts, memory_id))
            self._audit(db, "soft_archive", memory_id, {"reason": reason})
        self.append_archive({"type": "soft_archive", "reason": reason, "memory": value})
        return {"status": "archived", "id": memory_id}

    def patrol(self, namespace: str = "default") -> dict[str, Any]:
        with self.connect() as db:
            conflicts = [dict(row) for row in db.execute("SELECT * FROM conflict_reviews WHERE namespace=? AND status='open' ORDER BY created_at", (namespace,))]
            stale = [dict(row) for row in db.execute("SELECT id,fact_key,content,updated_at FROM memories WHERE namespace=? AND version_status='current' AND pinned=0 AND julianday('now')-julianday(updated_at)>180 ORDER BY updated_at LIMIT 100", (namespace,))]
            candidates = [dict(row) for row in db.execute("SELECT id,fact_key,content,known_at FROM memories WHERE namespace=? AND version_status='candidate' ORDER BY known_at", (namespace,))]
            report = {"generated_at": now_iso(), "namespace": namespace, "mode": "report_only", "conflicts": conflicts, "stale": stale, "candidates": candidates, "deleted": 0}
            self._audit(db, "patrol_report", None, {"conflicts": len(conflicts), "stale": len(stale), "candidates": len(candidates), "deleted": 0})
        self.append_archive({"type": "patrol_report", "report": report})
        return report

    def export(self, namespace: str = "default") -> dict[str, Any]:
        with self.connect() as db:
            return {
                "format": "xinhuo-v1",
                "exported_at": now_iso(),
                "memories": [self._row(row) for row in db.execute("SELECT * FROM memories WHERE namespace=? ORDER BY created_at", (namespace,))],
                "raw_events": [dict(row) for row in db.execute("SELECT * FROM raw_events WHERE namespace=? ORDER BY created_at", (namespace,))],
                "conflict_reviews": [dict(row) for row in db.execute("SELECT * FROM conflict_reviews WHERE namespace=? ORDER BY created_at", (namespace,))],
            }

    def glossary_set(self, term: str, definition: str) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("INSERT INTO glossary VALUES(?,?,?) ON CONFLICT(term) DO UPDATE SET definition=excluded.definition,updated_at=excluded.updated_at", (term, definition, now_iso()))
        return {"term": term, "definition": definition}

    def thought_add(self, content: str, mood: str | None = None) -> dict[str, Any]:
        content = str(content or "").strip()
        if not content:
            raise ValueError("content is required")
        thought_id = f"thk_{uuid.uuid4().hex}"
        with self.connect() as db:
            db.execute(
                "INSERT INTO thoughts(id,content,created_at,mood,status,resolved_at) VALUES(?,?,?,?,'open',NULL)",
                (thought_id, content, now_iso(), mood),
            )
            row = db.execute("SELECT * FROM thoughts WHERE id=?", (thought_id,)).fetchone()
        return dict(row)

    def thought_list(self, status: str | None = "open", limit: int = 50) -> list[dict[str, Any]]:
        sql = "SELECT * FROM thoughts"
        args: list[Any] = []
        if status:
            sql += " WHERE status=?"
            args.append(str(status))
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(max(1, min(500, int(limit))))
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args)]

    def thought_resolve(self, thought_id: str) -> dict[str, Any]:
        with self.connect() as db:
            cur = db.execute(
                "UPDATE thoughts SET status='resolved',resolved_at=? WHERE id=?",
                (now_iso(), thought_id),
            )
            if cur.rowcount == 0:
                raise KeyError("thought not found")
            row = db.execute("SELECT * FROM thoughts WHERE id=?", (thought_id,)).fetchone()
        return dict(row)
