"""Shared, atomic worker configuration. Secrets are never returned to the browser."""
import fcntl
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROLES = {
    'memory-curation': ('记忆整理', '提取、整理、情景与每日印象生成', 'generation', 'MEMORY_WORKER_MODEL'),
    'memory-review': ('独立复核', '审核证据、冲突和召回选择', 'generation', 'MEMORY_JUDGE_MODEL'),
    'embedding': ('向量嵌入', '可选；服务需支持 /embeddings', 'embedding', 'MEMORY_EMBED_MODEL'),
    'reranker': ('检索重排序', '可选；服务需支持 /rerank', 'reranking', 'MEMORY_RERANK_MODEL'),
}
DEFAULTS = {'memory-curation': 'deepseek-ai/DeepSeek-V3.2', 'memory-review': 'Qwen/Qwen3-30B-A3B-Instruct-2507', 'embedding': 'BAAI/bge-m3', 'reranker': 'BAAI/bge-reranker-v2-m3'}


def path():
    return Path(os.getenv('XINHUO_WORKER_CONFIG', str(Path(os.getenv('MEMORY_STATE_DIR', './data')) / 'workers.json')))


def read():
    try:
        value = json.loads(path().read_text())
        if not isinstance(value, dict):
            raise ValueError('invalid_worker_config')
        return value
    except FileNotFoundError:
        return {}


def effective(role):
    saved = read().get(role)
    if saved is not None:
        return saved
    return {'endpoint': os.getenv('MEMORY_MODEL_BASE_URL', '').rstrip('/'), 'apiKey': os.getenv('MEMORY_MODEL_API_KEY', ''), 'model': os.getenv(ROLES[role][3], DEFAULTS[role]), 'provider': 'OpenAI 兼容', 'custom': ''}


def profiles():
    out = []
    for role, (name, description, kind, _) in ROLES.items():
        c = effective(role)
        out.append({'id': role, 'name': name, 'description': description, 'kind': kind, 'providers': ['OpenAI 兼容'], 'models': [], 'config': {**c, 'apiKey': '', 'hasApiKey': bool(c.get('apiKey'))}})
    return out


def save(role, incoming, clear=False):
    if role not in ROLES:
        raise ValueError('unknown_worker')
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_fd = os.open(str(p)+'.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        values = read()
        previous = effective(role)
        if clear:
            c = {**previous, 'apiKey': ''}
        else:
            c = {k: str(incoming.get(k, '')).strip() for k in ('endpoint', 'model', 'custom', 'provider', 'apiKey')}
            if c['provider'] != 'OpenAI 兼容':
                raise ValueError('unsupported_protocol')
            if c['model'] == 'custom':
                c['model'] = c['custom']
            c['custom'] = ''
            u = urlsplit(c['endpoint'])
            if u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password or u.query or u.fragment:
                raise ValueError('invalid_endpoint')
            if not c['model'] or len(c['model']) > 200 or len(c['apiKey']) > 4096 or len(c['endpoint']) > 2048:
                raise ValueError('invalid_model_config')
            c['endpoint'] = c['endpoint'].rstrip('/')
            c['apiKey'] = c['apiKey'] or previous.get('apiKey', '')
        values[role] = c
        if p.exists():
            backups = p.parent / 'config-backups'
            backups.mkdir(mode=0o700, exist_ok=True)
            target = backups / ('workers-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
            shutil.copyfile(p, target)
            target.chmod(0o600)
        fd, temp = tempfile.mkstemp(dir=p.parent, prefix='.workers-')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(values, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, p)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return {'saved': True, 'applies': 'next_request'}
