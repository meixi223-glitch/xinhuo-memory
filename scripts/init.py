#!/usr/bin/env python3
"""Generate a token locally. Never overwrite an existing secret or data file."""
import os
import secrets
from pathlib import Path
os.umask(0o077)
root = Path(os.getenv('MEMORY_STATE_DIR', './data'))
root.mkdir(parents=True, exist_ok=True)
p = root / 'access-token'
try:
    with p.open('x') as f:
        f.write(secrets.token_urlsafe(32)+'\n')
    print('Created data/access-token. Open this local file to copy your login token.')
except FileExistsError:
    print('Existing access-token preserved.')
import sys
if '--compose' in sys.argv:
    config=Path('.env')
    try:
        with config.open('x') as f:
            f.write('MEMORY_TOKEN='+p.read_text().strip()+'\nXINHUO_PORT=18200\nXINHUO_SECURE_COOKIE=0\nAFFECT_INTAKE_MODE=self_report\n')
        print('Created .env for Docker Compose. Existing files are never overwritten.')
    except FileExistsError:
        print('.env already exists; set its MEMORY_TOKEN before starting Compose.')
