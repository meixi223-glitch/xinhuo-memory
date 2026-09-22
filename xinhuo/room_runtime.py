"""Single entry point: HTTP room plus durable background worker, one local database."""
import os
import signal
import threading
import time
from pathlib import Path


def main():
    os.umask(0o077)
    root = Path(os.getenv('MEMORY_STATE_DIR', './data')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('MEMORY_DB', str(root / 'memory.sqlite3'))
    os.environ.setdefault('MEMORY_ARCHIVE_DIR', str(root / 'archive'))
    os.environ.setdefault('MEMORY_ROOT', str(root))
    os.environ.setdefault('READING_MEMORY_ROOT', str(root / 'reading'))
    os.environ.setdefault('AFFECT_INTAKE_MODE', 'self_report')
    os.environ.setdefault('XINHUO_WORKER_CONFIG', str(root / 'workers.json'))
    token = os.getenv('MEMORY_TOKEN', '').strip()
    token_file = root / 'access-token'
    if not token and token_file.exists():
        token = token_file.read_text().strip()
    if len(token) < 24:
        raise SystemExit('Set MEMORY_TOKEN (24+ characters), or run: python3 scripts/init.py')
    os.environ['MEMORY_TOKEN'] = token
    from room_server import Handler, STORE
    from memory_worker import Worker
    from room_config import effective
    from http.server import ThreadingHTTPServer
    stop = threading.Event()
    def work():
        worker = Worker(STORE)
        last_schedule = 0
        while not stop.is_set():
            try:
                if not all(effective(r)['endpoint'] for r in ('memory-curation', 'memory-review')):
                    stop.wait(3)
                    continue
                if time.monotonic() - last_schedule > 60:
                    worker.schedule()
                    last_schedule = time.monotonic()
                if not worker.step(schedule=False):
                    stop.wait(2)
            except Exception as exc:
                print('worker_cycle_failed:'+type(exc).__name__, flush=True)
                stop.wait(5)
    thread = threading.Thread(target=work, name='memory-worker', daemon=True)
    server = ThreadingHTTPServer((os.getenv('MEMORY_HOST', '127.0.0.1'), int(os.getenv('MEMORY_PORT', '18200'))), Handler)
    server.daemon_threads = True
    def shutdown(*_):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    thread.start()
    print('Xinhuo room ready; worker waits for model configuration.', flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        thread.join(timeout=120)
        server.server_close()


if __name__ == '__main__':
    main()
