#!/usr/bin/env sh
cd "$(dirname "$0")"
[ -f .env ] || { echo "Run ./setup.sh first"; exit 1; }
PORT=${PORT:-8000}
echo "Ops Center: http://127.0.0.1:$PORT   (Ctrl+C stops it)"
exec .venv/bin/python -m fastapi dev --port "$PORT"
