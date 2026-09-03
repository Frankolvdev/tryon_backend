#!/usr/bin/env bash
set -euo pipefail
python3 /opt/ComfyUI/main.py --listen 127.0.0.1 --port 8188 &
COMFY_PID=$!
for _ in $(seq 1 120); do
  curl -fsS http://127.0.0.1:8188/system_stats >/dev/null && break
  sleep 1
done
python3 /opt/tryon/runpod_worker/handler.py
wait $COMFY_PID
