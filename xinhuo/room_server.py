"""Authenticated same-origin frontend. No browser persistence of credentials."""
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
import server as backend
from memory_models import Models
from memory_v2 import SECRET
from room_config import profiles, save, effective
from room_snapshot import snapshot, emotion_config, entries, entry

STORE = backend.STORE
SESSIONS = {}
ATTEMPTS = {}
LOCK = threading.Lock()
STATIC = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
ERRORS = {'invalid_endpoint': '请填写不含账号密码、查询参数的 HTTP(S) API 地址。', 'invalid_model_config': '请填写有效的模型 ID。', 'unsupported_protocol': '当前支持 OpenAI 兼容接口。', 'credential_like_content_rejected': '内容疑似包含凭据，请移除后重试。'}


class Handler(backend.Handler):
    server_version = 'XinhuoRoom/2.0'

    def log_message(self, *_):
        pass  # Paths, queries, payloads and tokens never enter access logs.

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def session_key(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookie.get('xinhuo_session')
            return hashlib.sha256(token.value.encode()).hexdigest() if token else ''
        except Exception:
            return ''

    def authorized(self):
        path = urlsplit(self.path).path
        if not backend.TOKEN: return False
        supplied = self.headers.get('Authorization', '')
        if hmac.compare_digest(supplied.encode(), ('Bearer '+backend.TOKEN).encode()): return True
        # Keep restricted review/wake token routes scoped; never accept query tokens.
        scoped = backend.CONTINUITY_REVIEW_TOKEN if path in ('/continuity/latent/review', '/continuity/trajectory/state') else backend.WAKE_TOKEN if path in ('/affect/wake-policy', '/affect/wake-mood', '/affect/self-report') else ''
        if scoped and hmac.compare_digest(supplied.encode(), ('Bearer '+scoped).encode()): return True
        if not path.startswith('/api/'): return False
        with LOCK:
            return SESSIONS.get(self.session_key(), 0) > time.time()

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == '/health':
            return self.send_json(200, {'ok': True, 'service': 'xinhuo-room', 'version': 2})
        if path.startswith('/api/'):
            if not self.authorized(): return self.send_json(401, {'error': '请使用部署时设置的 Token 登录。'})
            try:
                q = parse_qs(parsed.query)
                if path == '/api/session': return self.send_json(200, {'authenticated': True})
                if path == '/api/snapshot': return self.send_json(200, snapshot(STORE, backend.FRAMES))
                if path == '/api/emotions': return self.send_json(200, emotion_config(STORE))
                if path == '/api/workers': return self.send_json(200, profiles())
                if path == '/api/entries': return self.send_json(200, entries(STORE, min(1000000,max(0,int(q.get('offset',[0])[0]))), str(q.get('query',[''])[0])[:200]))
                if path == '/api/candidates': return self.send_json(200, STORE.browse({'status':'candidate','limit':100}))
                if path == '/api/composite-rules': return self.send_json(200, STORE.affect.composite_rules())
                if path == '/api/notes':
                    with STORE.connect() as db:
                        row = db.execute("SELECT value_json FROM memory_state WHERE key='room_daily_notes'").fetchone()
                    return self.send_json(200, json.loads(row[0]) if row else {})
                return self.send_json(404, {'error':'not_found'})
            except Exception:
                return self.send_json(500, {'error':'暂时无法读取，请重试。'})
        if path in ('/events/window', '/situation-frames/latest'):
            return super().do_GET()
        if path != '/' and not path.startswith('/assets/') and path != '/favicon.ico':
            return self.send_json(404, {'error':'not_found'})
        target = (STATIC / ('index.html' if path == '/' else unquote(path).lstrip('/'))).resolve()
        if not target.is_relative_to(STATIC) or not target.is_file():
            return self.send_json(404, {'error':'请先运行 npm ci --prefix frontend && npm run build --prefix frontend'})
        body = target.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlsplit(self.path).path
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            return self.send_json(403, {'error':'cross_origin_denied'})
        if path != '/api/login' and not self.authorized():
            return self.send_json(401, {'error':'请重新登录。'})
        if not self.headers.get('Content-Type','').startswith('application/json'):
            return self.send_json(415, {'error':'JSON required'})
        try:
            size = int(self.headers.get('Content-Length','0'))
            if size < 0 or size > 256*1024: return self.send_json(413, {'error':'request_too_large'})
            data = json.loads(self.rfile.read(size) or '{}')
            if not isinstance(data,dict): raise ValueError('object_required')
            if path == '/api/login': return self.login(data)
            if path == '/api/logout':
                with LOCK: SESSIONS.pop(self.session_key(), None)
                self.send_response(200)
                self.send_header('Set-Cookie', 'xinhuo_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
                self.end_headers()
                return
            if path.startswith('/api/workers/'):
                parts = path.split('/')
                role = parts[3]
                if len(parts)==5 and parts[4]=='test':
                    c = effective(role)
                    if not c['endpoint']: raise ValueError('model_not_configured')
                    m = Models()
                    if role=='embedding':
                        v = m.embed(['Connection test'])
                        if not v or not v[0]: raise ValueError('invalid_embedding')
                    elif role=='reranker':
                        m.rerank('test',['test','other'],1)
                    else:
                        result,_ = m.json('Return {"ok":true}.', {'connection_test':True}, worker=role=='memory-curation',timeout=20,max_tokens=40)
                        if result.get('ok') is not True: raise ValueError('invalid_test_response')
                    return self.send_json(200, {'ok':True})
                return self.send_json(200, save(role, data, clear=data.get('clearApiKey') is True))
            if path == '/api/notes':
                import re
                day,text = str(data.get('day','')),str(data.get('text',''))
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or len(text)>5000: raise ValueError('invalid_note')
                if SECRET.search(text): raise ValueError('credential_like_content_rejected')
                with STORE.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    row=db.execute("SELECT value_json FROM memory_state WHERE key='room_daily_notes'").fetchone()
                    notes=json.loads(row[0]) if row else {}
                    notes[day]=text
                    db.execute("INSERT OR REPLACE INTO memory_state VALUES('room_daily_notes',?)",(json.dumps(notes,ensure_ascii=False),))
                return self.send_json(200,notes)
            if path == '/api/tool':
                name = data.get('name')
                args = data.get('arguments') or {}
                if name not in {'memory_upsert','memory_recall','memory_review','memory_archive','memory_restore','memory_pin','memory_organize','memory_get','mood_composite_rule_set'}:
                    return self.send_json(403, {'error':'tool_not_allowed'})
                if SECRET.search(json.dumps(args,ensure_ascii=False)): raise ValueError('credential_like_content_rejected')
                args={**args,'namespace':'default'}
                value=backend.call_tool(name,args)
                return self.send_json(200,value)
            if path == '/api/events': path='/events'
            if path == '/events':
                if SECRET.search(str(data.get('content',''))): raise ValueError('credential_like_content_rejected')
                result=backend.ingest_with_window(data)
                return self.send_json(200,result)
            if path == '/situation-frames/refresh':
                if SECRET.search(json.dumps(data,ensure_ascii=False)): raise ValueError('credential_like_content_rejected')
                return self.send_json(201,backend.FRAMES.write(data))
            # Existing REST/MCP implementation consumes the already parsed object.
            import io
            raw=json.dumps(data).encode()
            original=self.rfile
            self.rfile=io.BytesIO(raw)
            del self.headers['Content-Length']
            self.headers['Content-Length']=str(len(raw))
            try: return super().do_POST()
            finally: self.rfile=original
        except Exception as exc:
            code=str(exc)
            message=ERRORS.get(code, '操作未完成，请检查输入与服务配置。')
            # Provider bodies/exception details may contain secrets. Only generic status escapes.
            if type(exc).__name__=='ModelUnavailable': message='模型连接失败，请核对 API 地址、密钥、模型 ID 及对应接口支持。'
            return self.send_json(400, {'error':message})

    def login(self,data):
        ip=self.client_address[0]
        now=time.time()
        with LOCK:
            for k in list(ATTEMPTS):
                if ATTEMPTS[k][1]<now-600: del ATTEMPTS[k]
            attempts,start=ATTEMPTS.get(ip,(0,now))
            if attempts>=10: return self.send_json(429,{'error':'尝试次数过多，请在十分钟后重试。'})
            ATTEMPTS[ip]=(attempts+1,start)
        if not backend.TOKEN or not hmac.compare_digest(str(data.get('token','')).encode(),backend.TOKEN.encode()):
            return self.send_json(401,{'error':'Token 不正确。'})
        token=secrets.token_urlsafe(32)
        with LOCK:
            ATTEMPTS.pop(ip,None)
            for k in list(SESSIONS):
                if SESSIONS[k]<now: del SESSIONS[k]
            if len(SESSIONS)>1000: SESSIONS.pop(next(iter(SESSIONS)))
            SESSIONS[hashlib.sha256(token.encode()).hexdigest()]=now+12*3600
        self.send_response(200)
        secure='; Secure' if os.getenv('XINHUO_SECURE_COOKIE')=='1' else ''
        self.send_header('Set-Cookie',f'xinhuo_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200{secure}')
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(b'{"authenticated":true}')
