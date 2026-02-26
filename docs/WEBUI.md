# Web UI

Dashboard backend: `webui/server.py`.

## API
- `GET /api/events?limit=200` — recent decoded events
- `GET /api/live` — SSE live stream
- `GET /api/host_metrics` — latest host metrics (if configured)

## UI features
- Decoder health summary cards:
  - health status (ok/warn/error mix)
  - 5-minute average confidence
  - 5-minute error summary (with top error code)
  - decode rate (/min)
- Event table with confidence context:
  - status, score, confidence, error count
  - row coloring by status
- Drill-down panel:
  - click row to view event JSON details (quality/errors/decode/frame)
- Filters:
  - sensor id
  - minimum score
  - status
  - warn/error only
- Export:
  - filtered CSV export button

## Run
```bash
python3 webui/server.py --jsonl /path/to/rx_events_*.jsonl --host 0.0.0.0 --port 8088
```

With host metrics + auto-follow latest event file:
```bash
python3 webui/server.py --jsonl /path/to/current/rx_events_*.jsonl --jsonl-follow-dir /home/cdomotor/rf_log --host-metrics-jsonl /path/to/host_metrics.jsonl --host 0.0.0.0 --port 8088
```

## Design notes
- Decoupled from GNU Radio runtime.
- No bokeh dependency.
- Can run as a persistent systemd service (`fwlab-webui.service`).
