#!/usr/bin/env python3
from __future__ import annotations

import json
import hmac
import os
import traceback
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from memory_core import structured_payload
from memory_v2 import MemoryStore, SECRET
from event_window import EventWindowStore
from situation_frames import SituationFrameStore

HOST = os.environ.get("MEMORY_HOST", "127.0.0.1")
PORT = int(os.environ.get("MEMORY_PORT", "18200"))
TOKEN = os.environ.get("MEMORY_TOKEN", "")
WAKE_TOKEN = os.environ.get("AFFECT_WAKE_TOKEN", "")
CONTINUITY_REVIEW_TOKEN = os.environ.get("MEMORY_CONTINUITY_REVIEW_TOKEN", "")
STORE = MemoryStore(os.environ.get("MEMORY_DB", "./data/memory.sqlite3"), os.environ.get("MEMORY_ARCHIVE_DIR", "./data/archive"))
EVENTS = EventWindowStore(STORE.db_path)
FRAMES = SituationFrameStore(STORE.db_path)

TOOLS = [
    ("continuity_status", "查看连续性副脑统计；不读取事实库全文"),
    ("continuity_recall", "读取有证据的未完轨迹与近场；潜在便签仅审核通过后可见，历史材料不构成授权"),
    ("continuity_trajectories", "查看有证据的未完话题与判断变化轨迹"),
    ("continuity_nearfield", "查看最近3-7天、自动过期的轻量近场背景"),
    ("continuity_latents", "查看来源可追溯的潜在便签及审核状态"),
    ("memory_daily", "查看整日印象、来源和次日唤醒节奏影响"),
    ("mood_status", "读取当前多维表达状态；只作参考，不推断用户授权"),
    ("mood_history", "分页查看表达状态变化和依据，不修改状态"),
    ("mood_why", "读取主模型自评的理由、原文证据与动态复合情绪名称"),
    ("mood_self_report", "主模型仅在操作性情绪显著变化时提交有原文证据的自评"),
    ("mood_composite_rules", "读取可编辑的复合情绪命名规则"),
    ("mood_composite_rule_set", "新增或更新复合情绪命名规则；只组合八种基础情绪"),
    ("memory_restore", "恢复尘封记忆为1点权重和30天保护；遇到新事实冲突转待核对"),
    ("memory_status", "查看记忆统计与后台整理任务，不读取全部记忆"),
    ("memory_evidence", "按event_id查看相关原始对话证据"),
    ("memory_browse", "分页浏览完整记忆与历史"),
    ("memory_recalls", "查看记忆调用、选择理由与注入量"),
    ("memory_review", "审核候选记忆 approve/reject；replace加replaces_id可采用候选并保留旧版本"),
    ("memory_organize", "请求后台整理；立即返回持久任务id"),
    ("memory_search", "Search current memories with strength, time and emotion ranking"),
    ("memory_recall", "Hybrid full-text, vector and bounded 1-3 hop relation-path recall"),
    ("memory_list", "List current memories; history is opt-in"),
    ("memory_get", "Get one memory by id"),
    ("memory_history", "Trace every version for a fact key"),
    ("memory_upsert", "Create a memory; changed facts become review candidates"),
    ("memory_supersede", "Explicitly supersede an old memory with a new version"),
    ("memory_ingest", "Append a raw event without interpretation"),
    ("memory_pin", "Pin or unpin a memory"),
    ("memory_archive", "Soft-archive a memory"),
    ("memory_delete", "Compatibility alias for soft archive; never hard deletes"),
    ("memory_export", "Export memories, raw events and conflict reviews"),
    ("memory_patrol", "Generate a report-only integrity patrol"),
    ("memory_boot", "Return pinned and strongest current memories"),
    ("glossary_set", "Set a glossary definition"),
    ("diary_get", "List recent diary memories"),
    ("thought_add", "Add a thought to the open thought pool"),
    ("thought_list", "List thoughts (default: open only)"),
    ("thought_resolve", "Mark a thought resolved by id"),
]

# memory_upsert 写入必须带情绪；仅 kind=diary 与 capsule/自动化 ingest 写入豁免。
MOOD_EXEMPT_SOURCES = {"trusted_compact", "capsule", "auto", "automation", "ingest", "patrol"}


def require_mood(args: dict) -> None:
    kind = str(args.get("kind") or args.get("type") or "fact")
    source = str(args.get("source") or "bridge")
    if kind == "diary" or source in MOOD_EXEMPT_SOURCES:
        return
    label = str(args.get("emotion_label") or "").strip()
    try:
        intensity = int(args.get("emotion_intensity"))
    except (TypeError, ValueError):
        intensity = None
    if not label or intensity is None or not (1 <= intensity <= 5):
        raise ValueError("emotion_label 必填且非空，emotion_intensity 必须为 1-5 的整数（仅 kind=diary 或 capsule/自动化写入豁免）")


def schema_for(name: str) -> dict:
    common = {"namespace": {"type": "string"}}
    if name in {"continuity_status","continuity_trajectories","continuity_nearfield","continuity_latents"}:
        return {"type":"object","properties":{**common,"status":{"type":"string"},"limit":{"type":"integer"},"include_evidence":{"type":"boolean"}}}
    if name == "continuity_recall":
        return {"type":"object","properties":{**common,"query":{"type":"string"},"context":{"type":"string"},"limit":{"type":"integer"},"budget_tokens":{"type":"integer"}},"required":["query"]}
    if name in {"memory_status", "memory_recalls", "memory_organize", "memory_browse", "mood_status", "mood_history", "mood_why", "memory_daily"}:
        return {"type":"object","properties":{**common,"query":{"type":"string"},"status":{"type":"string"},"layer":{"type":"string"},"offset":{"type":"integer"},"limit":{"type":"integer"}}}
    if name == "mood_self_report":
        return {"type":"object","properties":{**common,"session_id":{"type":"string"},"turn_id":{"type":"string"},"source_msg_id":{"type":"string"},"model":{"type":"string"},"valence":{"type":"number","minimum":-1,"maximum":1},"arousal":{"type":"number","minimum":-1,"maximum":1},"dims":{"type":"object","description":"Only joy/sadness/fear/anger/surprise/disgust/anticipation/trust; each -0.18..0.18","additionalProperties":{"type":"number","minimum":-.18,"maximum":.18}},"relationships":{"type":"object","description":"Separate intimacy/longing/desire/companionship group; each -0.18..0.18","additionalProperties":{"type":"number","minimum":-.18,"maximum":.18}},"reason":{"type":"string","maxLength":80},"evidence":{"type":"array","items":{"type":"string"},"minItems":1},"confidence":{"type":"number","minimum":0,"maximum":1},"stated_at":{"type":"string"}},"required":["model","valence","arousal","reason","evidence","confidence","stated_at"]}
    if name == "mood_composite_rules":return {"type":"object","properties":{}}
    if name == "mood_composite_rule_set":
        return {"type":"object","properties":{"id":{"type":"string"},"name":{"type":"string"},"components":{"type":"array","items":{"type":"string"},"minItems":2,"maxItems":4},"min_component":{"type":"number"},"min_total":{"type":"number"},"priority":{"type":"integer"},"enabled":{"type":"boolean"}},"required":["id","name","components"]}
    if name == "memory_evidence": return {"type":"object","properties":{**common,"event_id":{"type":"string"}},"required":["event_id"]}
    if name == "memory_review": return {"type":"object","properties":{"id":{"type":"string"},"action":{"type":"string","enum":["approve","reject","replace"]},"replaces_id":{"type":"string"}},"required":["id","action"]}
    if name in {"memory_search", "memory_recall"}:
        props = {**common, "query": {"type": "string"}, "limit": {"type": "integer"}, "include_history": {"type": "boolean"}, "graph_depth": {"type":"integer","minimum":0,"maximum":3,"description":"0 disables relation expansion; default 3"}}
        return {"type": "object", "properties": props, "required": ["query"]}
    if name == "memory_list":
        return {"type": "object", "properties": {**common, "limit": {"type": "integer"}, "include_history": {"type": "boolean"}}}
    if name == "memory_get":
        return {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
    if name == "memory_history":
        return {"type": "object", "properties": {**common, "fact_key": {"type": "string"}}, "required": ["fact_key"]}
    if name in {"memory_archive", "memory_delete", "memory_restore"}:
        return {"type": "object", "properties": {"id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["id"]}
    if name == "memory_pin":
        return {"type": "object", "properties": {"id": {"type": "string"}, "pinned": {"type": "boolean"}}, "required": ["id"]}
    if name == "memory_supersede":
        return {"type": "object", "properties": {"old_id": {"type": "string"}, "content": {"type": "string"}, "occurred_at": {"type": "string"}}, "required": ["old_id", "content"]}
    if name == "memory_ingest":
        return {"type": "object", "properties": {**common, "session_id": {"type": "string"}, "role": {"type": "string"}, "content": {"type": "string"}, "occurred_at": {"type": "string"}}, "required": ["content"]}
    if name == "glossary_set":
        return {"type": "object", "properties": {"term": {"type": "string"}, "definition": {"type": "string"}}, "required": ["term", "definition"]}
    if name == "memory_upsert":
        return {"type": "object", "properties": {**common, "content": {"type": "string"}, "layer": {"type":"string","enum":["core","semantic","episodic","procedural","experience"]}, "summary":{"type":"string"}, "source_event_id":{"type":"string"}, "source":{"type":"string"}, "fact_key": {"type": "string"}, "occurred_at": {"type": "string"}, "known_at": {"type": "string"}, "strength": {"type": "number"}, "importance": {"type": "number"}, "emotion_label": {"type": "string"}, "emotion_intensity": {"type": "integer"}, "emotion_selfreport_id":{"type":"string"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["content"]}
    if name == "thought_add":
        return {"type": "object", "properties": {"content": {"type": "string"}, "mood": {"type": "string"}}, "required": ["content"]}
    if name == "thought_list":
        return {"type": "object", "properties": {"status": {"type": "string"}, "limit": {"type": "integer"}}}
    if name == "thought_resolve":
        return {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
    return {"type": "object", "properties": common}


def ingest_with_window(data):
    if SECRET.search(str(data.get('content') or '')):
        raise ValueError('credential_like_content_rejected')
    # Validate the event-window timestamp before writing the raw event.
    from event_window import utc_iso
    if data.get('occurred_at'): utc_iso(data['occurred_at'])
    result = STORE.ingest_event(data)
    if not result.get('duplicate'):
        EVENTS.ingest({**data, 'event_id': result['id']}, source_raw_event_id=result['id'])
        STORE.enqueue('situation_frame', {'event_id': result['id']}, 'situation:'+result['id'])
    return result


def call_tool(name: str, args: dict):
    ns = str(args.get("namespace") or "default")
    if name == "continuity_status": return STORE.continuity.status(ns)
    if name == "continuity_recall": return STORE.continuity.pack({**args,"namespace":ns},record_recall=False)
    if name == "continuity_trajectories": return STORE.continuity.list("trajectory",ns,str(args.get("status") or ""),args.get("limit",30),bool(args.get("include_evidence")))
    if name == "continuity_nearfield": return STORE.continuity.list("nearfield",ns,"",args.get("limit",30),bool(args.get("include_evidence")))
    if name == "continuity_latents": return STORE.continuity.list("latent",ns,str(args.get("status") or ""),args.get("limit",30),bool(args.get("include_evidence")))
    if name in {"memory_search", "memory_recall"}: return STORE.recall_pack({**args,"namespace":ns,"mode":"explicit"})
    if name == "memory_daily": return STORE.daily.browse(int(args.get("limit",30)),int(args.get("offset",0)))
    if name == "mood_status": return STORE.affect.snapshot(ns)
    if name == "mood_history": return STORE.affect.history(ns,int(args.get("limit",80)),int(args.get("offset",0)))
    if name == "mood_why": return STORE.affect.why(ns,int(args.get("limit",20)))
    if name == "mood_self_report": return STORE.affect.apply_self_report({**args,"namespace":ns})
    if name == "mood_composite_rules": return STORE.affect.composite_rules()
    if name == "mood_composite_rule_set": return STORE.affect.set_composite_rule(args)
    if name == "memory_restore": return STORE.retention.restore(str(args["id"]))
    if name == "memory_status": return STORE.overview(ns)
    if name == "memory_browse": return STORE.browse(args)
    if name == "memory_recalls": return STORE.recalls(ns,int(args.get("offset",0)),int(args.get("limit",30)))
    if name == "memory_evidence": return STORE.evidence(str(args["event_id"]),ns)
    if name == "memory_review": return STORE.review(str(args["id"]),str(args["action"]),args.get("replaces_id"))
    if name == "memory_organize":
        return {"job_id":STORE.enqueue("enrich_batch",{"ids":[m["id"] for m in STORE.list(ns,False,16)]}),"status":"queued"}
    if name == "memory_list":
        return STORE.list(ns, bool(args.get("include_history")), args.get("limit", 50))
    if name == "memory_get":
        value=STORE.get(str(args["id"]))
        if not args.get("inspect_only"):STORE.retention.touch([str(args["id"])])
        return value
    if name == "memory_history": return STORE.history(str(args["fact_key"]), ns)
    if name == "memory_upsert":
        if args.get("emotion_selfreport_id"):
            emotion=STORE.affect.memory_emotion(str(args["emotion_selfreport_id"]),ns)
            args={**args,"emotion_label":emotion["label"],"emotion_intensity":emotion["intensity"]}
        require_mood(args)
        return STORE.upsert(args)
    if name == "memory_supersede": return STORE.supersede(str(args["old_id"]), args)
    if name == "memory_ingest": return ingest_with_window(args)
    if name == "memory_pin": return STORE.pin(str(args["id"]), bool(args.get("pinned", True)))
    if name in {"memory_archive", "memory_delete"}: return STORE.archive(str(args["id"]), str(args.get("reason") or name))
    if name == "memory_export": return STORE.export(ns)
    if name == "memory_patrol": return STORE.patrol(ns)
    if name == "memory_boot": return STORE.boot(ns)
    if name == "glossary_set": return STORE.glossary_set(str(args["term"]), str(args["definition"]))
    if name == "diary_get": return [x for x in STORE.list(ns, False, args.get("limit", 20)) if x["kind"] == "diary"]
    if name == "thought_add": return STORE.thought_add(str(args["content"]), args.get("mood"))
    if name == "thought_list": return STORE.thought_list(args.get("status", "open"), args.get("limit", 50))
    if name == "thought_resolve": return STORE.thought_resolve(str(args["id"]))
    raise ValueError(f"unknown tool: {name}")


class Handler(BaseHTTPRequestHandler):
    server_version = "Xinhuo/1.0"

    def log_message(self, fmt, *args):
        message = re.sub(r"([?&]token=)[^\s]+", r"\1<redacted>", fmt % args)
        print(f"[memory-http] {self.address_string()} {message}", flush=True)

    def send_json(self, status: int, payload: object):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self) -> bool:
        path=urlparse(self.path).path
        if path in ("/continuity/latent/review","/continuity/trajectory/state"):
            supplied=self.headers.get("Authorization","")
            return bool(CONTINUITY_REVIEW_TOKEN) and hmac.compare_digest(supplied,f"Bearer {CONTINUITY_REVIEW_TOKEN}")
        if WAKE_TOKEN and urlparse(self.path).path in ("/affect/wake-policy", "/affect/wake-mood", "/affect/self-report") and self.headers.get("Authorization", "")==f"Bearer {WAKE_TOKEN}":return True
        if not TOKEN:
            return True
        query_token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}" or query_token == TOKEN

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self.send_json(200, {"ok": True, "service": "xinhuo", "storage": "sqlite", "mode": "current-by-default"})
        if not self.authorized():
            return self.send_json(401, {"error": "unauthorized"})
        try:
            if parsed.path == "/events/window":
                query = parse_qs(parsed.query)
                from_utc = str((query.get("from") or [""])[0])
                to_utc = str((query.get("to") or [""])[0])
                if not from_utc or not to_utc:
                    raise ValueError("from and to are required UTC timestamps")
                channel = str((query.get("channel") or [""])[0]).strip() or None
                return self.send_json(200, EVENTS.window(from_utc, to_utc, channel))
            if parsed.path == "/situation-frames/latest":
                frame = FRAMES.latest()
                return self.send_json(200, {"frame": frame, "fresh": bool(frame and not frame["stale"])})
        except Exception as exc:
            return self.send_json(400, {"error": str(exc)})
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if not self.authorized():
            return self.send_json(401, {"error": "unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 256*1024: return self.send_json(413, {"error":"request_too_large"})
            data = json.loads(self.rfile.read(length) or b"{}")
            path = urlparse(self.path).path
            if path == "/affect/state": return self.send_json(200, STORE.affect.snapshot(str(data.get("namespace") or "default")))
            if path == "/affect/wake-policy": return self.send_json(200, STORE.daily.wake_policy())
            if path == "/affect/wake-mood":
                mood = call_tool("mood_status", {})
                return self.send_json(200, {"vector": {key: mood["vector"][key] for key in ("longing", "sharing", "companionship")}})
            if path == "/affect/self-report": return self.send_json(200, STORE.affect.apply_self_report(data))
            if path == "/affect/tool": return self.send_json(200, STORE.affect.observe_tool(data))
            if path == "/usage": return self.send_json(200, STORE.retention.touch(list(data.get("ids") or [])[:15],str(data.get("receipt") or "")[:200] or None))
            if path == "/recall": return self.send_json(200, STORE.recall_pack(data))
            if path == "/recall/commit": return self.send_json(200, STORE.commit_recall(str(data.get("id",""))))
            if path == "/recall/reset":
                base=STORE.reset_seen(str(data.get("session_key","")));STORE.continuity.reset_seen(str(data.get("session_key","")));return self.send_json(200,base)
            if path == "/continuity": return self.send_json(200, STORE.continuity.pack(data))
            if path == "/continuity/commit": return self.send_json(200, STORE.continuity.commit(str(data.get("id",""))))
            if path == "/continuity/latent/review": return self.send_json(200, STORE.continuity.review_latent(str(data.get("id","")),str(data.get("action","")),str(data.get("note") or ""),str(data.get("namespace") or "default")))
            if path == "/continuity/trajectory/state": return self.send_json(200, STORE.continuity.set_trajectory_state(str(data.get("id","")),str(data.get("state","")),str(data.get("namespace") or "default")))
            if path == "/boot": return self.send_json(200, STORE.boot(str(data.get("namespace","default"))))
            if path == "/events":
                raw_event = ingest_with_window(data)
                return self.send_json(200, raw_event)
            if path == "/situation-frames/refresh":
                return self.send_json(201, FRAMES.write(data))
            if path == "/capsule": return self.send_json(200, STORE.sync_capsule(data))
            if path == "/patrol": return self.send_json(200, STORE.patrol(str(data.get("namespace") or "default")))
            if path == "/mcp": return self.handle_mcp(data)
            return self.send_json(404, {"error": "not found"})
        except Exception as exc:
            self.send_json(400, {"error": "invalid_request", "kind": type(exc).__name__})

    def handle_mcp(self, request: dict):
        request_id = request.get("id")
        method = request.get("method")
        if method == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "xinhuo", "version": "1.0.0"}}
        elif method == "notifications/initialized":
            return self.send_json(202, {})
        elif method == "tools/list":
            result = {"tools": [{"name": name, "description": desc, "inputSchema": schema_for(name)} for name, desc in TOOLS]}
        elif method == "tools/call":
            params = request.get("params") or {}
            value = call_tool(str(params.get("name") or ""), params.get("arguments") or {})
            result = {
                "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
                "structuredContent": structured_payload(value),
            }
        else:
            return self.send_json(200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}})
        self.send_json(200, {"jsonrpc": "2.0", "id": request_id, "result": result})


if __name__ == "__main__":
    print(f"xinhuo listening on {HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
