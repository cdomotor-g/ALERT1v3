#!/usr/bin/env python3
import argparse
import json
import os
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


HTML = """<!doctype html><html><head><meta charset='utf-8'><title>ALERT1v3 Dashboard</title>
<style>body{font-family:Arial;margin:1rem;background:#10151c;color:#d7e0ea}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #243243;padding:.4rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}.muted{color:#93a6b8}input{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}</style></head>
<body><h2>ALERT1v3 Live Dashboard</h2><div class='card'>Status: <span id='status'>starting</span> · Events loaded: <span id='count'>0</span> · Filter sensor: <input id='sensor' placeholder='optional'></div>
<table><thead><tr><th>Time</th><th>Status</th><th>Sensor</th><th>Format</th><th>Data</th><th>Summary</th></tr></thead><tbody id='rows'></tbody></table>
<script>
const rows=document.getElementById('rows'); const status=document.getElementById('status'); const count=document.getElementById('count');
const sensor=document.getElementById('sensor'); let events=[];
function render(){const f=sensor.value.trim(); rows.innerHTML=''; let shown=0; for(const ev of events.slice().reverse()){if(f && String(ev.decode?.sensor_id??'')!==f) continue; shown++; const tr=document.createElement('tr'); tr.innerHTML=`<td>${ev.ts||''}</td><td>${ev.status||''}</td><td>${ev.decode?.sensor_id??''}</td><td>${ev.decode?.format_id??''}</td><td>${ev.decode?.data_val??''}</td><td>${ev.summary||''}</td>`; rows.appendChild(tr); if(shown>=100) break;} count.textContent=String(events.length);} sensor.addEventListener('input',render);
fetch('/api/events?limit=200').then(r=>r.json()).then(d=>{events=d.events||[]; render();});
const es=new EventSource('/api/live'); es.onmessage=(m)=>{try{events.push(JSON.parse(m.data)); if(events.length>1000) events=events.slice(-1000); render(); status.textContent='live';}catch{}}; es.onerror=()=>status.textContent='reconnecting';
</script></body></html>"""


class EventStore:
    def __init__(self, jsonl_path: Path, max_events: int = 2000):
        self.path = jsonl_path
        self.events = deque(maxlen=max_events)
        self.offset = 0
        self._initial_load()

    def _initial_load(self):
        if not self.path.exists():
            return
        with self.path.open('r', encoding='utf-8', errors='replace') as f:
            for line in f:
                self._append_line(line)
            self.offset = f.tell()

    def _append_line(self, line: str):
        line = line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except Exception:
            return
        if isinstance(event, dict):
            self.events.append(event)

    def poll_new(self):
        if not self.path.exists():
            return []
        new_events = []
        with self.path.open('r', encoding='utf-8', errors='replace') as f:
            f.seek(self.offset)
            for line in f:
                before = len(self.events)
                self._append_line(line)
                if len(self.events) > before:
                    new_events.append(self.events[-1])
            self.offset = f.tell()
        return new_events


class Handler(BaseHTTPRequestHandler):
    store: EventStore = None

    def _json(self, obj, code=200):
        payload = json.dumps(obj, default=str).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/':
            payload = HTML.encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/api/events':
            q = parse_qs(parsed.query)
            limit = int(q.get('limit', ['100'])[0])
            limit = max(1, min(limit, 1000))
            events = list(self.store.events)[-limit:]
            return self._json({'events': events, 'count': len(self.store.events)})

        if parsed.path == '/api/live':
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            try:
                while True:
                    new_events = self.store.poll_new()
                    for ev in new_events:
                        self.wfile.write(f"data: {json.dumps(ev, default=str)}\n\n".encode('utf-8'))
                    self.wfile.flush()
                    time.sleep(1.0)
            except (BrokenPipeError, ConnectionResetError):
                return

        self.send_error(HTTPStatus.NOT_FOUND)


def main():
    p = argparse.ArgumentParser(description='ALERT1v3 web dashboard server')
    p.add_argument('--jsonl', required=True, help='Path to rx_events_*.jsonl')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8088)
    args = p.parse_args()

    store = EventStore(Path(args.jsonl))
    Handler.store = store

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Listening on http://{args.host}:{args.port} using {args.jsonl}')
    server.serve_forever()


if __name__ == '__main__':
    main()
