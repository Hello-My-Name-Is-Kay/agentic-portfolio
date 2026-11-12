#!/bin/sh
# Build the AgentCore direct-code zip: ARM64 (Graviton) Linux wheels for Python 3.12, no Docker needed.
# Only the two local packages are built from source; they are pure Python.
# Usage (from the repository root): sh flagship-agent/deploy/build_code_zip.sh build/agent.zip
set -eu
out=${1:?output zip path}
work=$(mktemp -d)
uv pip install --quiet --target "$work" --python-version 3.12 --python-platform aarch64-manylinux_2_28 \
    ./mock-booking-api "./flagship-agent[agentcore]"
cp flagship-agent/deploy/main.py "$work/main.py"
python3 - "$work" "$out" <<'PY'
import os, sys, zipfile
src, out = sys.argv[1], os.path.abspath(sys.argv[2])
os.makedirs(os.path.dirname(out), exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, src))
print(out, round(os.path.getsize(out) / 1e6, 1), "MB")
PY
rm -rf "$work"
