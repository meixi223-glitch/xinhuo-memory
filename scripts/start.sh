#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
python3 scripts/init.py
npm ci --prefix frontend
npm run build --prefix frontend
exec python3 xinhuo/room_runtime.py
