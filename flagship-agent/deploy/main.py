"""Entry file for AgentCore Runtime direct code deployment (the zip built by ``deploy/build_code_zip.sh``).

Starts the mock booking API on localhost in a background thread (demo only: its SQLite data lives as long as the
microVM), then serves the agent on 0.0.0.0:8080. The container image does the same with ``start.sh``.
"""

import os
import threading
import time
import urllib.request

os.environ.setdefault("BOOKING_DB_PATH", "/tmp/booking.db")
os.environ.setdefault("AGENT_BOOKING_API_BASE", "http://127.0.0.1:8000")

import uvicorn  # noqa: E402
from booking_api.main import app as booking_app  # noqa: E402


def _serve_booking_api() -> None:
    uvicorn.run(booking_app, host="127.0.0.1", port=8000, log_level="warning")


threading.Thread(target=_serve_booking_api, daemon=True).start()
for _ in range(50):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
        break
    except OSError:
        time.sleep(0.2)

from agent.agentcore import main  # noqa: E402

main()
