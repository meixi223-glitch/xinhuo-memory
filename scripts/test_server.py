"""Disposable server for browser tests; never opens an existing memory database."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='xinhuo-browser-test-') as temp:
    env={**os.environ,'MEMORY_STATE_DIR':temp,'MEMORY_DB':temp+'/memory.sqlite3','MEMORY_ARCHIVE_DIR':temp+'/archive','XINHUO_WORKER_CONFIG':temp+'/workers.json','MEMORY_HOST':'127.0.0.1','MEMORY_PORT':'18391','MEMORY_TOKEN':'browser-fixture-token-not-a-real-secret','MEMORY_MODEL_BASE_URL':'','MEMORY_MODEL_API_KEY':'','AFFECT_INTAKE_MODE':'self_report'}
    proc=subprocess.Popen([sys.executable,'xinhuo/room_runtime.py'],cwd=Path(__file__).resolve().parents[1],env=env)
    try:proc.wait()
    finally:
        proc.terminate()
        proc.wait(timeout=150)
