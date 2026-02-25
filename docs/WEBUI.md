# Web UI MVP (Issue #6)

A decoupled dashboard backend is provided at `webui/server.py`.

## Features
- REST endpoint for recent events: `GET /api/events?limit=200`
- SSE live stream endpoint: `GET /api/live`
- Built-in minimal dashboard (status + recent table + sensor filter)
- Reads structured events from logger JSONL output (`rx_events_*.jsonl`)

## Run
```bash
python3 webui/server.py --jsonl /path/to/rx_events_*.jsonl --host 0.0.0.0 --port 8088
```

Open:
- `http://<host>:8088/`

## Design notes
- No GNU Radio runtime coupling.
- No bokeh dependency.
- Can run alongside receiver process.
