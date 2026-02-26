#!/usr/bin/env python3
import argparse
import json
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


HTML = """<!doctype html><html><head><meta charset='utf-8'><title>FW-LAB Dashboard</title>
<style>
body{font-family:Arial;margin:1rem;background:#10151c;color:#d7e0ea}
table{width:100%;border-collapse:collapse}
th,td{border-bottom:1px solid #243243;padding:.4rem}
.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}
.muted{color:#93a6b8}
input,select{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}
.grid{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:.6rem;margin-bottom:.8rem}
.good{color:#6dd17c}.warn{color:#f2c14e}.bad{color:#f36f6f}
tr.ok{background:rgba(75,160,98,.10)}
tr.warn{background:rgba(220,170,80,.12)}
tr.error{background:rgba(200,80,80,.14)}
#detail pre{white-space:pre-wrap;word-break:break-word;background:#0f141a;padding:.6rem;border-radius:6px;border:1px solid #2a3948;max-height:240px;overflow:auto}
.small{font-size:.9em}
</style></head>
<body>
<h2>FW-LAB Live Dashboard</h2>
<div class='card'>
  Status: <span id='status'>starting</span> · Events loaded: <span id='count'>0</span>
  · Sensor: <input id='sensor' placeholder='sensor id' style='width:90px'>
  · Min score: <input id='minScore' type='number' min='0' max='1' step='0.05' placeholder='0.0' style='width:72px'>
  · Status: <select id='statusFilter'><option value=''>all</option><option value='ok'>ok</option><option value='warn'>warn</option><option value='error'>error</option></select>
  · <label><input type='checkbox' id='warnOnly'> warn/error only</label>
  · <button id='exportBtn'>Export filtered CSV</button>
</div>

<div class='grid'>
  <div class='card'><div class='muted small'>Decoder health</div><div id='sum-health'>n/a</div></div>
  <div class='card'><div class='muted small'>Confidence (5m avg)</div><div id='sum-conf'>-</div></div>
  <div class='card'><div class='muted small'>Errors (5m)</div><div id='sum-errs'>-</div></div>
  <div class='card'><div class='muted small'>Decode rate (/min)</div><div id='sum-rate'>-</div></div>
</div>

<div class='card'>
  Host metrics: <span id='hm-status' class='muted'>n/a</span> · CPU <span id='hm-cpu'>-</span>% · RAM <span id='hm-mem'>-</span>% · Disk <span id='hm-disk'>-</span>% · Temp <span id='hm-temp'>-</span>°C · Load/core <span id='hm-load'>-</span> · Breaches <span id='hm-breach'>0</span>
</div>

<table><thead><tr><th>Time</th><th>Status</th><th>Score</th><th>Conf</th><th>Errs</th><th>Sensor</th><th>Format</th><th>Data</th><th>Summary</th></tr></thead><tbody id='rows'></tbody></table>

<div id='detail' class='card' style='margin-top:.8rem'>
  <div class='muted'>Drill-down (click a row)</div>
  <pre id='detailText'>No event selected.</pre>
</div>

<script>
const rows=document.getElementById('rows'); const status=document.getElementById('status'); const count=document.getElementById('count');
const sensor=document.getElementById('sensor'); const minScore=document.getElementById('minScore'); const statusFilter=document.getElementById('statusFilter'); const warnOnly=document.getElementById('warnOnly');
const exportBtn=document.getElementById('exportBtn');
const detailText=document.getElementById('detailText');
let events=[];

function classForStatus(s){ if(s==='ok') return 'good'; if(s==='warn') return 'warn'; return 'bad'; }

function computeSummary(){
  const now = Date.now();
  const recent = events.filter(e=>{
    const t = Date.parse(e.ts||'');
    return isFinite(t) ? (now - t) <= 5*60*1000 : false;
  });
  if(!recent.length){
    document.getElementById('sum-health').textContent='n/a';
    document.getElementById('sum-conf').textContent='-';
    document.getElementById('sum-errs').textContent='-';
    document.getElementById('sum-rate').textContent='0.0';
    return;
  }
  const st = {ok:0,warn:0,error:0};
  let scoreN=0, scoreSum=0, errCnt=0;
  const codeCount={};
  for(const e of recent){
    const s=e.status||'ok'; st[s]=(st[s]||0)+1;
    const q=e.quality?.score;
    if(typeof q==='number'){ scoreN++; scoreSum+=q; }
    const errs=Array.isArray(e.errors)?e.errors:[];
    errCnt += errs.length;
    for(const er of errs){ const c=er?.code||'unknown'; codeCount[c]=(codeCount[c]||0)+1; }
  }
  const health = st.error>0 ? 'ERROR' : (st.warn>0 ? 'WARN' : 'OK');
  const healthEl = document.getElementById('sum-health');
  healthEl.textContent = `${health} (ok:${st.ok||0} warn:${st.warn||0} err:${st.error||0})`;
  healthEl.className = classForStatus(health.toLowerCase());
  document.getElementById('sum-conf').textContent = scoreN ? (scoreSum/scoreN).toFixed(3) : 'n/a';
  let top='none',topN=0; for(const [k,v] of Object.entries(codeCount)){ if(v>topN){topN=v; top=k;} }
  document.getElementById('sum-errs').textContent = `${errCnt} total${topN?` · top ${top} (${topN})`:''}`;
  document.getElementById('sum-rate').textContent = ((recent.length/5.0)).toFixed(2);
}

function passFilter(ev){
  const f=sensor.value.trim(); if(f && String(ev.decode?.sensor_id??'')!==f) return false;
  const sf=statusFilter.value; if(sf && (ev.status||'')!==sf) return false;
  if(warnOnly.checked && (ev.status==='ok' || !ev.status)) return false;
  const ms=minScore.value.trim();
  if(ms){
    const v=Number(ms); const q=ev.quality?.score;
    if(typeof q==='number' && q < v) return false;
  }
  return true;
}

function render(){
  rows.innerHTML=''; let shown=0;
  for(const ev of events.slice().reverse()){
    if(!passFilter(ev)) continue;
    shown++;
    const tr=document.createElement('tr');
    tr.className = ev.status || '';
    const q = (typeof ev.quality?.score==='number') ? ev.quality.score.toFixed(3) : '';
    const c = ev.quality?.confidence || '';
    const errs = Array.isArray(ev.errors) ? ev.errors.length : 0;
    tr.innerHTML=`<td>${ev.ts||''}</td><td>${ev.status||''}</td><td>${q}</td><td>${c}</td><td>${errs}</td><td>${ev.decode?.sensor_id??''}</td><td>${ev.decode?.format_id??''}</td><td>${ev.decode?.data_val??''}</td><td>${ev.summary||''}</td>`;
    tr.addEventListener('click',()=>{
      detailText.textContent = JSON.stringify({
        ts: ev.ts,
        status: ev.status,
        summary: ev.summary,
        quality: ev.quality,
        errors: ev.errors,
        decode: ev.decode,
        frame: { payload_hex: ev.frame?.payload_hex, bits_preview: (ev.frame?.payload_bits||'').slice(0,128) }
      }, null, 2);
    });
    rows.appendChild(tr);
    if(shown>=150) break;
  }
  count.textContent=String(events.length);
  computeSummary();
}

[sensor,minScore,statusFilter,warnOnly].forEach(el=>el.addEventListener('input',render));
exportBtn.addEventListener('click',()=>{
  const filtered = events.filter(passFilter);
  const header = ['ts','status','quality_score','quality_confidence','errors_count','sensor_id','format_id','data_val','summary','error_codes'];
  const rows = filtered.map(ev=>[
    ev.ts||'', ev.status||'',
    (typeof ev.quality?.score==='number')?ev.quality.score:'',
    ev.quality?.confidence||'',
    Array.isArray(ev.errors)?ev.errors.length:0,
    ev.decode?.sensor_id??'', ev.decode?.format_id??'', ev.decode?.data_val??'',
    (ev.summary||'').replaceAll(',', ';'),
    (Array.isArray(ev.errors)?ev.errors.map(e=>e.code||'').join('|'):'')
  ]);
  const csv = [header.join(',')].concat(rows.map(r=>r.map(x=>`"${String(x).replaceAll('"','""')}"`).join(','))).join('\n');
  const blob = new Blob([csv], {type:'text/csv;charset=utf-8;'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'fwlab_filtered_events.csv';
  a.click();
  URL.revokeObjectURL(url);
});
fetch('/api/events?limit=400').then(r=>r.json()).then(d=>{events=d.events||[]; render();});

function renderHost(m){
  document.getElementById('hm-status').textContent = m?.status || 'n/a';
  const mm = m?.metrics || {};
  document.getElementById('hm-cpu').textContent = (mm.cpu_percent ?? '-');
  document.getElementById('hm-mem').textContent = (mm.mem_percent ?? '-');
  document.getElementById('hm-disk').textContent = (mm.disk_percent ?? '-');
  document.getElementById('hm-temp').textContent = (mm.temp_c ?? '-');
  document.getElementById('hm-load').textContent = (mm.load_1m_per_core ?? '-');
  document.getElementById('hm-breach').textContent = String((m?.breaches || []).length);
}
fetch('/api/host_metrics').then(r=>r.json()).then(d=>renderHost(d.event||null)).catch(()=>{});
setInterval(()=>fetch('/api/host_metrics').then(r=>r.json()).then(d=>renderHost(d.event||null)).catch(()=>{}),3000);

const es=new EventSource('/api/live');
es.onmessage=(m)=>{ try{ events.push(JSON.parse(m.data)); if(events.length>2000) events=events.slice(-2000); render(); status.textContent='live'; }catch{} };
es.onerror=()=>status.textContent='reconnecting';
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
    host_metrics_store: EventStore = None

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
            limit = max(1, min(limit, 2000))
            events = list(self.store.events)[-limit:]
            return self._json({'events': events, 'count': len(self.store.events)})

        if parsed.path == '/api/host_metrics':
            if not self.host_metrics_store:
                return self._json({'event': None, 'enabled': False})
            self.host_metrics_store.poll_new()
            ev = list(self.host_metrics_store.events)[-1] if self.host_metrics_store.events else None
            return self._json({'event': ev, 'enabled': True})

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
    p = argparse.ArgumentParser(description='FW-LAB web dashboard server')
    p.add_argument('--jsonl', required=True, help='Path to rx_events_*.jsonl')
    p.add_argument('--host-metrics-jsonl', default='', help='Optional path to host_metrics.jsonl')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8088)
    args = p.parse_args()

    store = EventStore(Path(args.jsonl))
    Handler.store = store

    if args.host_metrics_jsonl:
        Handler.host_metrics_store = EventStore(Path(args.host_metrics_jsonl), max_events=200)
    else:
        Handler.host_metrics_store = None

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Listening on http://{args.host}:{args.port} using {args.jsonl}')
    if args.host_metrics_jsonl:
        print(f'Host metrics source: {args.host_metrics_jsonl}')
    server.serve_forever()


if __name__ == '__main__':
    main()
