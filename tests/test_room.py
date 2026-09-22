"""Black-box deployment checks, with isolated SQLite and a local model fixture."""
import http.cookiejar
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOKEN='fixture-room-token-not-a-real-secret-12345'

class Provider(BaseHTTPRequestHandler):
    calls=[]
    def log_message(self,*_):pass
    def do_POST(self):
        d=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path,d.get('model'),self.headers.get('Authorization')))
        if self.path.endswith('/embeddings'):
            result={'data':[{'index':i,'embedding':[0.2,0.8]} for i,_ in enumerate(d['input'])]}
        elif self.path.endswith('/rerank'):
            result={'results':[{'index':0,'relevance_score':.99}]}
        else:
            prompt=d['messages'][0]['content'];data=json.loads(d['messages'][1]['content'])
            answer={'ok':True}
            if '提取具体共同经历' in prompt:
                event=next(e for e in data['events'] if e['role']=='user')
                answer={'memories':[{'content':event['content'],'summary':'周末去植物园','layer':'episodic','fact_key':'fixture-garden','evidence':[{'event_id':event['id'],'quote':event['content']}],'tags':['植物园']}]}
            elif 'approved_indices' in prompt:answer={'approved_indices':list(range(len(data.get('candidates',[]))))}
            elif '概括当前事件窗' in prompt:answer={'focus':'周末去植物园','phase':'计划中','transition':'','evidence_event_ids':[data['events'][-1]['id']]}
            elif '核对情景摘要' in prompt:answer={'approved':True}
            elif '制作检索索引' in prompt:answer={'items':[]}
            elif '连续性副脑' in prompt:answer={'trajectories':[],'nearfield':[],'latents':[]}
            result={'choices':[{'message':{'content':json.dumps(answer,ensure_ascii=False)}}],'usage':{}}
        b=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b)

class RoomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        cls.thread=threading.Thread(target=cls.provider.serve_forever,daemon=True);cls.thread.start()
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        cls.base=f'http://127.0.0.1:{port}'
        env={**os.environ,'MEMORY_TOKEN':TOKEN,'MEMORY_PORT':str(port),'MEMORY_HOST':'127.0.0.1','MEMORY_STATE_DIR':cls.tmp.name,'MEMORY_DB':cls.tmp.name+'/memory.sqlite3','MEMORY_ARCHIVE_DIR':cls.tmp.name+'/archive','XINHUO_WORKER_CONFIG':cls.tmp.name+'/workers.json','MEMORY_MODEL_BASE_URL':'','MEMORY_MODEL_API_KEY':'','AFFECT_INTAKE_MODE':'self_report'}
        cls.proc=subprocess.Popen([sys.executable,'xinhuo/room_runtime.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.jar=http.cookiejar.CookieJar();cls.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cls.jar))
        for _ in range(100):
            try:urllib.request.urlopen(cls.base+'/health',timeout=1);break
            except Exception:time.sleep(.05)
        else:raise RuntimeError('server_not_ready')
    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate();cls.proc.wait(timeout=150);cls.provider.shutdown();cls.provider.server_close();cls.tmp.cleanup()
    def req(self,path,data=None,client=None,headers=None):
        r=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with (client or self.client).open(r,timeout=30) as result:return result.status,json.loads(result.read() or '{}'),result.headers
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read() or '{}'),e.headers
    def test_01_auth_empty_and_no_credential_egress(self):
        self.assertEqual(self.req('/api/snapshot')[0],401)
        self.assertEqual(self.req('/api/login',{'token':'incorrect'})[0],401)
        status,_,headers=self.req('/api/login',{'token':TOKEN});self.assertEqual(status,200)
        self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        status,data,_=self.req('/api/snapshot');self.assertEqual(status,200);self.assertEqual(data['source'],'live');self.assertEqual(data['entries'],[]);self.assertIsNone(data['mood']['v'])
        self.assertEqual(self.req('/api/notes',{'day':'2026-09-22','text':'fixture'},headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.req('/api/events',{'content':'Bearer fixture-private-value'})[0],400)
        self.assertEqual(self.req('/api/snapshot?token='+TOKEN,client=urllib.request.build_opener())[0],401)
    def test_02_configuration_reaches_provider_and_worker(self):
        for role in ('memory-curation','memory-review','embedding','reranker'):
            cfg={'provider':'OpenAI 兼容','endpoint':f'http://127.0.0.1:{self.provider.server_port}/v1','apiKey':'fixture-key-'+role,'model':'fixture-'+role,'custom':''}
            self.assertEqual(self.req('/api/workers/'+role,cfg)[0],200)
            self.assertEqual(self.req('/api/workers/'+role+'/test',{})[0],200)
        data=self.req('/api/workers')[1]
        self.assertNotIn('fixture-key',json.dumps(data));self.assertTrue(all(p['config']['hasApiKey'] for p in data))
        self.assertEqual(Path(self.tmp.name+'/workers.json').stat().st_mode&0o777,0o600)
        self.assertEqual(len(Provider.calls),4)
        content='我们计划周末去植物园，看温室里的植物。'
        payload={'content':content,'source_msg_id':'fixture-event','session_id':'fixture','channel':'chat'}
        self.assertEqual(self.req('/api/events',payload)[0],200)
        self.assertTrue(self.req('/api/events',payload)[1]['duplicate'])
        for _ in range(200):
            with sqlite3.connect(self.tmp.name+'/memory.sqlite3') as db:
                count=db.execute('SELECT count(*) FROM memories').fetchone()[0]
                frames=db.execute('SELECT count(*) FROM situation_frames').fetchone()[0]
            if count and frames:break
            time.sleep(.1)
        self.assertGreater(count,0);self.assertGreater(frames,0)
        snap=self.req('/api/snapshot')[1]
        self.assertEqual(snap['stats']['events'],1);self.assertTrue(any(e['kind']=='memory' for e in snap['entries']))
        self.assertEqual(snap['scene']['focus'],'周末去植物园');self.assertEqual(snap['scene']['body'],'')
        self.assertIn('/v1/chat/completions',[c[0] for c in Provider.calls])
    def test_03_notes_pagination_and_logout(self):
        self.assertEqual(self.req('/api/notes',{'day':'2026-09-22','text':'人的补充'})[0],200)
        self.assertEqual(self.req('/api/notes')[1]['2026-09-22'],'人的补充')
        self.assertTrue(self.req('/api/entries?query='+urllib.parse.quote('植物园'))[1]['items'])
        status,_,_=self.req('/api/logout',{});self.assertEqual(status,200)
        self.assertEqual(self.req('/api/snapshot')[0],401)

if __name__=='__main__':unittest.main()
