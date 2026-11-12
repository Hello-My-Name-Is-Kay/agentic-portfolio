#!/bin/sh
# The mock booking API runs beside the agent on localhost (demo only: its SQLite data lives as long as the microVM).
set -eu
uvicorn booking_api.main:app --host 127.0.0.1 --port 8000 --log-level warning &
python - <<'PY'
import time, urllib.request
for _ in range(50):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
        break
    except OSError:
        time.sleep(0.2)
PY
exec agent-agentcore
