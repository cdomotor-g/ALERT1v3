# Host monitoring (Raspberry Pi)

FW-LAB includes a lightweight sidecar monitor for Pi resource usage.

Scripts:
- `sidecars/perf/monitor.py` (canonical)
- `tools/host_monitor.py` (compatibility wrapper)

Outputs:
- JSONL file (default): `rf_log/host_metrics.jsonl`
- Optional MQTT topic: `<prefix>/rx/host_metrics`
- Warning surfacing topic on threshold breach: `<prefix>/rx/status`

Collected metrics:
- CPU usage %
- RAM usage %
- Disk usage % (`/`)
- CPU temperature (thermal zone / vcgencmd fallback)
- Load averages + 1m load per core

Status and thresholds:
- Each sample includes `status: ok|warn`
- `breaches` array lists threshold violations

## Example run

```bash
python3 tools/host_monitor.py \
  --interval 5 \
  --output-jsonl rf_log/host_metrics.jsonl \
  --warn-cpu 85 \
  --warn-mem 85 \
  --warn-disk 90 \
  --warn-temp 75 \
  --warn-load 1.25
```

## With MQTT publish

```bash
python3 tools/host_monitor.py \
  --mqtt-host 127.0.0.1 \
  --mqtt-port 1883 \
  --mqtt-topic-prefix alert
```

## Helper runner (monitor + web)

Use the helper script to launch monitor and web dashboard together:

```bash
./tools/run_stack_with_monitor.sh
```

Environment overrides:
- `LOG_BASE`
- `EVENTS_JSONL`
- `HOST_METRICS_JSONL`
- `WEB_HOST`
- `WEB_PORT`
- `MON_INTERVAL`

## Soak/trend summary

Create a summary report from collected metrics:

```bash
python3 tools/host_metrics_summary.py \
  --jsonl rf_log/host_metrics.jsonl \
  --out rf_log/host_metrics_summary.json
```

## Web dashboard integration

Start web UI with host metrics enabled:

```bash
python3 webui/server.py \
  --jsonl rf_log/<DATE>/rx_events_<TIME>.jsonl \
  --host-metrics-jsonl rf_log/host_metrics.jsonl \
  --host 0.0.0.0 --port 8088
```

Dashboard card will show latest host metrics + breach count.
