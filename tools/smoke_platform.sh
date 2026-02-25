#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[smoke] py_compile core components"
python3 -m py_compile \
  webui/server.py \
  tools/platform_capabilities.py \
  tools/host_monitor.py \
  sidecars/perf/monitor.py \
  sidecars/perf/adapters/linux_proc.py \
  tools/host_metrics_summary.py

echo "[smoke] platform capabilities"
python3 tools/platform_capabilities.py

echo "[smoke] OK"
