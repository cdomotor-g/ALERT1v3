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
input,select,button{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}
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
  · <button id='resetBtn'>Reset filters</button>
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
(function(){
  function g(o,k,d){ return (o && o[k]!==undefined && o[k]!==null) ? o[k] : d; }
  function escCSV(v){ return ('"'+String(v).replace(/"/g,'""')+'"'); }

  var rows=document.getElementById('rows');
  var status=document.getElementById('status');
  var count=document.getElementById('count');
  var sensor=document.getElementById('sensor');
  var minScore=document.getElementById('minScore');
  var statusFilter=document.getElementById('statusFilter');
  var warnOnly=document.getElementById('warnOnly');
  var resetBtn=document.getElementById('resetBtn');
  var exportBtn=document.getElementById('exportBtn');
  var detailText=document.getElementById('detailText');
  var events=[];

  function classForStatus(s){ if(s==='ok') return 'good'; if(s==='warn') return 'warn'; return 'bad'; }

  function computeSummary(){
    var now = Date.now();
    var recent = [];
    for(var i=0;i<events.length;i++){
      var t=Date.parse(g(events[i],'ts',''));
      if(isFinite(t) && (now-t)<=300000) recent.push(events[i]);
    }
    if(!recent.length){
      document.getElementById('sum-health').textContent='n/a';
      document.getElementById('sum-conf').textContent='-';
      document.getElementById('sum-errs').textContent='-';
      document.getElementById('sum-rate').textContent='0.0';
      return;
    }
    var st={ok:0,warn:0,error:0}, scoreN=0, scoreSum=0, errCnt=0, codeCount={};
    for(var j=0;j<recent.length;j++){
      var e=recent[j]; var s=g(e,'status','ok'); st[s]=(st[s]||0)+1;
      var q=g(g(e,'quality',{}),'score',null); if(typeof q==='number'){ scoreN++; scoreSum+=q; }
      var errs=g(e,'errors',[]); if(!errs || !errs.length) errs=[];
      errCnt += errs.length;
      for(var k=0;k<errs.length;k++){ var c=g(errs[k],'code','unknown'); codeCount[c]=(codeCount[c]||0)+1; }
    }
    var health = st.error>0 ? 'ERROR' : (st.warn>0 ? 'WARN' : 'OK');
    var healthEl=document.getElementById('sum-health');
    healthEl.textContent=health+' (ok:'+st.ok+' warn:'+st.warn+' err:'+st.error+')';
    healthEl.className=classForStatus(health.toLowerCase());
    document.getElementById('sum-conf').textContent = scoreN ? (scoreSum/scoreN).toFixed(3) : 'n/a';
    var top='none',topN=0; for(var key in codeCount){ if(codeCount[key]>topN){topN=codeCount[key]; top=key;} }
    document.getElementById('sum-errs').textContent = errCnt+' total'+(topN?(' · top '+top+' ('+topN+')'):'');
    document.getElementById('sum-rate').textContent = (recent.length/5.0).toFixed(2);
  }

  function passFilter(ev){
    var f=sensor.value.trim();
    var de=g(ev,'decode',{});
    if(f && String(g(de,'sensor_id',''))!==f) return false;
    var sf=statusFilter.value; if(sf && g(ev,'status','')!==sf) return false;
    if(warnOnly.checked && g(ev,'status','ok')==='ok') return false;
    var ms=minScore.value.trim();
    if(ms){
      var v=Number(ms), q=g(g(ev,'quality',{}),'score',null);
      if(typeof q==='number' && q < v) return false;
    }
    return true;
  }

  function render(){
    rows.innerHTML='';
    var shown=0;
    for(var i=events.length-1;i>=0;i--){
      var ev=events[i];
      if(!passFilter(ev)) continue;
      shown++;
      var tr=document.createElement('tr');
      tr.className = g(ev,'status','');
      var q=g(g(ev,'quality',{}),'score',null); q=(typeof q==='number') ? q.toFixed(3) : '';
      var c=g(g(ev,'quality',{}),'confidence','');
      var errs=g(ev,'errors',[]); var errN=(errs&&errs.length)?errs.length:0;
      var de=g(ev,'decode',{});
      tr.innerHTML='<td>'+g(ev,'ts','')+'</td><td>'+g(ev,'status','')+'</td><td>'+q+'</td><td>'+c+'</td><td>'+errN+'</td><td>'+g(de,'sensor_id','')+'</td><td>'+g(de,'format_id','')+'</td><td>'+g(de,'data_val','')+'</td><td>'+g(ev,'summary','')+'</td>';
      (function(evt){ tr.addEventListener('click', function(){
        var fr=g(evt,'frame',{});
        detailText.textContent = JSON.stringify({
          ts:g(evt,'ts',''), status:g(evt,'status',''), summary:g(evt,'summary',''),
          quality:g(evt,'quality',{}), errors:g(evt,'errors',[]), decode:g(evt,'decode',{}),
          frame:{ payload_hex:g(fr,'payload_hex',''), bits_preview:String(g(fr,'payload_bits','')).slice(0,128) }
        }, null, 2);
      }); })(ev);
      rows.appendChild(tr);
      if(shown>=150) break;
    }
    count.textContent=String(events.length);
    computeSummary();
  }

  function exportCSV(){
    var filtered=[];
    for(var i=0;i<events.length;i++) if(passFilter(events[i])) filtered.push(events[i]);
    var lines=['"ts","status","quality_score","quality_confidence","errors_count","sensor_id","format_id","data_val","summary","error_codes"'];
    for(var j=0;j<filtered.length;j++){
      var ev=filtered[j], de=g(ev,'decode',{}), q=g(ev,'quality',{}), errs=g(ev,'errors',[]);
      var errCodes=[]; for(var k=0;k<errs.length;k++) errCodes.push(g(errs[k],'code',''));
      var row=[g(ev,'ts',''),g(ev,'status',''),g(q,'score',''),g(q,'confidence',''),errs.length||0,g(de,'sensor_id',''),g(de,'format_id',''),g(de,'data_val',''),g(ev,'summary',''),errCodes.join('|')];
      for(var r=0;r<row.length;r++) row[r]=escCSV(row[r]);
      lines.push(row.join(','));
    }
    var blob = new Blob([lines.join('\\n')], {type:'text/csv;charset=utf-8;'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a'); a.href=url; a.download='fwlab_filtered_events.csv'; a.click(); URL.revokeObjectURL(url);
  }

  function resetFilters(){ sensor.value=''; minScore.value=''; statusFilter.value=''; warnOnly.checked=false; render(); }

  sensor.addEventListener('input',render);
  minScore.addEventListener('input',render);
  statusFilter.addEventListener('input',render);
  warnOnly.addEventListener('input',render);
  exportBtn.addEventListener('click',exportCSV);
  resetBtn.addEventListener('click',resetFilters);

  fetch('/api/events?limit=400').then(function(r){return r.json();}).then(function(d){events=d.events||[]; render();});

  function renderHost(m){
    document.getElementById('hm-status').textContent = g(m,'status','n/a');
    var mm=g(m,'metrics',{});
    document.getElementById('hm-cpu').textContent = g(mm,'cpu_percent','-');
    document.getElementById('hm-mem').textContent = g(mm,'mem_percent','-');
    document.getElementById('hm-disk').textContent = g(mm,'disk_percent','-');
    document.getElementById('hm-temp').textContent = g(mm,'temp_c','-');
    document.getElementById('hm-load').textContent = g(mm,'load_1m_per_core','-');
    document.getElementById('hm-breach').textContent = String((g(m,'breaches',[])||[]).length);
  }

  function pollHost(){ fetch('/api/host_metrics').then(function(r){return r.json();}).then(function(d){ renderHost(g(d,'event',null)); })['catch'](function(){}); }
  pollHost(); setInterval(pollHost,3000);

  var es=new EventSource('/api/live');
  es.onmessage=function(m){
    try{ events.push(JSON.parse(m.data)); if(events.length>2000) events=events.slice(-2000); render(); status.textContent='live'; }
    catch(e){}
  };
  es.onerror=function(){ status.textContent='reconnecting'; };
})();
</script></body></html>"""


class EventStore:
    def __init__(self, jsonl_path: Path, max_events: int = 2000, follow_latest_in: Path | None = None):
        self.path = jsonl_path
        self.events = deque(maxlen=max_events)
        self.offset = 0
        self.follow_latest_in = follow_latest_in
        self._last_scan = 0.0
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

    def _maybe_switch_latest(self):
        if not self.follow_latest_in:
            return
        now = time.time()
        if now - self._last_scan < 2.0:
            return
        self._last_scan = now

        candidates = sorted(self.follow_latest_in.rglob('rx_events_*.jsonl'))
        if not candidates:
            return
        latest = candidates[-1]
        if latest == self.path:
            return

        self.path = latest
        self.offset = 0
        self.events.clear()
        self._initial_load()

    def poll_new(self):
        self._maybe_switch_latest()
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
    p.add_argument('--jsonl-follow-dir', default='', help='Optional directory to auto-follow latest rx_events_*.jsonl')
    p.add_argument('--host-metrics-jsonl', default='', help='Optional path to host_metrics.jsonl')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8088)
    args = p.parse_args()

    follow_dir = Path(args.jsonl_follow_dir) if args.jsonl_follow_dir else None
    store = EventStore(Path(args.jsonl), follow_latest_in=follow_dir)
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
