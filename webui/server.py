#!/usr/bin/env python3
import argparse
import json
import gzip
import time
import shutil
import subprocess
from datetime import datetime
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


HTML = """<!doctype html><html><head><meta charset='utf-8'><title>FW-LAB Dashboard</title>
<style>
body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}
.page{padding:1rem}
.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}
.muted{color:#93a6b8}
input,select,button{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}
.grid{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:.6rem;margin-bottom:.8rem}
.good{color:#6dd17c}.warn{color:#f2c14e}.bad{color:#f36f6f}

.sticky-wrap{position:sticky;top:0;z-index:50;background:#10151c;padding-top:.6rem}

.table-wrap{max-height:58vh;overflow:auto;border:1px solid #243243;border-radius:8px;background:#121922}
table{width:100%;border-collapse:collapse}
th,td{border-bottom:1px solid #243243;padding:.4rem}
thead th{position:sticky;top:0;background:#17212b;z-index:5}
tr.ok{background:rgba(75,160,98,.10)}
tr.warn{background:rgba(220,170,80,.12)}
tr.error{background:rgba(200,80,80,.14)}
tr.inline-detail td{background:#0f141a}
pre{white-space:pre-wrap;word-break:break-word;background:#0f141a;padding:.6rem;border-radius:6px;border:1px solid #2a3948;max-height:240px;overflow:auto}
.small{font-size:.9em}
</style>
<script src='https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'></script>
</head>
<body>
<div class='page'>
  <h2 style='margin-top:0'>FW-LAB Live Dashboard</h2>
  <div class='card' style='padding:.45rem .8rem'><strong>Navigation:</strong> <a href='/' style='color:#7fc8ff'>Dashboard</a> · <a href='/events' style='color:#7fc8ff'>Events</a> · <a href='/radio' style='color:#7fc8ff'>Radio</a> · <a href='/trends' style='color:#7fc8ff'>Trends</a> · <a href='/admin' style='color:#7fc8ff'>Admin</a></div>

  <div class='sticky-wrap'>
    <div class='card'>
      Status: <span id='status'>starting</span> · Receiver: <span id='rx-state' class='muted'>unknown</span> · Events loaded: <span id='count'>0</span> · Source: <span id='source' class='muted'>n/a</span>
    </div>

    <div class='grid'>
      <div class='card'><div class='muted small'>Decoder health</div><div id='sum-health'>n/a</div></div>
      <div class='card'><div class='muted small'>Confidence (5m avg)</div><div id='sum-conf'>-</div></div>
      <div class='card'><div class='muted small'>Errors (5m)</div><div id='sum-errs'>-</div></div>
      <div class='card'><div class='muted small'>Decode rate (/min)</div><div id='sum-rate'>-</div></div>
    </div>

    <div id='rx-section' class='card'>
      <div class='muted small'>Rx packets per 2 min (last 30 min)</div>
      <div id='rx-chart' style='height:150px'></div>
    </div>

    <div class='card'>
      Host metrics: <span id='hm-status' class='muted'>n/a</span> · CPU <span id='hm-cpu'>-</span>% · RAM <span id='hm-mem'>-</span>% · Disk <span id='hm-disk'>-</span>% · Temp <span id='hm-temp'>-</span>°C · Load/core <span id='hm-load'>-</span> · Breaches <span id='hm-breach'>0</span>
    </div>

    <div id='rf-controls-section' class='card'>
      RF now: Freq <span id='rf-freq-now'>-</span> Hz · Gain <span id='rf-gain-now'>-</span> dB · Squelch <span id='rf-sq-now'>-</span> dB<br>
      RF control (pending/apply on receiver restart):
      Freq <input id='rf-freq-set' style='width:140px' placeholder='173900000'>
      Gain <input id='rf-gain-set' style='width:80px' placeholder='-1'>
      Squelch <input id='rf-sq-set' style='width:80px' placeholder='-33'>
      <button id='rf-apply'>Save RF config</button>
      <button id='rx-start'>Start receiver</button>
      <button id='rx-stop'>Stop receiver</button>
      <button id='rx-restart'>Restart receiver</button>
      <span id='rf-msg' class='muted'></span>
    </div>

    <div class='card'>
      Storage: <span id='st-mode' class='muted'>n/a</span> · Used <span id='st-used'>-</span>% · Free <span id='st-free'>-</span> GB · Retention <span id='st-days'>-</span> days
    </div>

    <div id='detailTop' class='card'>
      <div class='muted'>Drill-down (click a row)</div>
      <pre id='detailText'>No event selected.</pre>
    </div>
  </div>

  <div id='data-section'>
  <div id='table-controls-card' class='card'>
    <span class='muted'>Table controls:</span>
    Sensor: <input id='sensor' placeholder='sensor id' style='width:90px'>
    · Min score: <input id='minScore' type='number' min='0' max='1' step='0.05' placeholder='0.0' style='width:72px'>
    · Status: <select id='statusFilter'><option value=''>all</option><option value='ok'>ok</option><option value='warn'>warn</option><option value='error'>error</option></select>
    · <label><input type='checkbox' id='warnOnly'> warn/error only</label>
    · <label><input type='checkbox' id='okOnly'> ok only (hide warn/error)</label>
    · Time: <select id='timeMode'><option value='local' selected>local</option><option value='zulu'>zulu</option></select>
    · Detail: <select id='detailMode'><option value='top' selected>top</option><option value='inline'>inline</option></select>
    · <button id='resetBtn'>Reset filters</button>
    · <button id='exportBtn'>Export filtered CSV</button>
  </div>
  <div class='table-wrap'>
    <table><thead><tr><th>Time</th><th>Status</th><th>Score</th><th>Conf</th><th>Errs</th><th>Sensor</th><th>Format</th><th>Data</th><th>Summary</th></tr></thead><tbody id='rows'></tbody></table>
  </div>
  </div>
</div>

<script>
(function(){
  function g(o,k,d){ return (o && o[k]!==undefined && o[k]!==null) ? o[k] : d; }
  function escCSV(v){ return ('"'+String(v).replace(/"/g,'""')+'"'); }

  var rows=document.getElementById('rows');
  var dataSection=document.getElementById('data-section');
  var tableControlsCard=document.getElementById('table-controls-card');
  var rxSection=document.getElementById('rx-section');
  var rfControlsSection=document.getElementById('rf-controls-section');
  var isEventsPage = (window.location.pathname === '/events');
  if(dataSection && !isEventsPage){ dataSection.style.display='none'; }
  if(tableControlsCard && !isEventsPage){ tableControlsCard.style.display='none'; }
  if(rxSection && isEventsPage){ rxSection.style.display='none'; }
  if(rfControlsSection && isEventsPage){ rfControlsSection.style.display='none'; }
  var status=document.getElementById('status');
  var rxState=document.getElementById('rx-state');
  var count=document.getElementById('count');
  var source=document.getElementById('source');
  var sensor=document.getElementById('sensor');
  var minScore=document.getElementById('minScore');
  var statusFilter=document.getElementById('statusFilter');
  var warnOnly=document.getElementById('warnOnly');
  var okOnly=document.getElementById('okOnly');
  var timeMode=document.getElementById('timeMode');
  var detailMode=document.getElementById('detailMode');
  var resetBtn=document.getElementById('resetBtn');
  var exportBtn=document.getElementById('exportBtn');
  var detailText=document.getElementById('detailText');
  var detailTop=document.getElementById('detailTop');
  if(detailTop && !isEventsPage){ detailTop.style.display='none'; }
  var rxChartEl=document.getElementById('rx-chart');
  var rxChart=(window.echarts && rxChartEl) ? echarts.init(rxChartEl) : null;
  var rfFreqNow=document.getElementById('rf-freq-now'), rfGainNow=document.getElementById('rf-gain-now'), rfSqNow=document.getElementById('rf-sq-now');
  var rfFreqSet=document.getElementById('rf-freq-set'), rfGainSet=document.getElementById('rf-gain-set'), rfSqSet=document.getElementById('rf-sq-set');
  var rfApply=document.getElementById('rf-apply'), rfMsg=document.getElementById('rf-msg');
  var rxStart=document.getElementById('rx-start'), rxStop=document.getElementById('rx-stop'), rxRestart=document.getElementById('rx-restart');
  var events=[];
  var inlineRow=null;
  var selectedDetailKey='';

  function fmtTs(ts){
    if(!ts) return '';
    var d=new Date(ts);
    if(!isFinite(d.getTime())) return ts;
    if(timeMode.value==='zulu') return d.toISOString();
    return d.toLocaleString();
  }

  function classForStatus(s){ if(s==='ok') return 'good'; if(s==='warn') return 'warn'; return 'bad'; }

  function drawRxBars(){
    if(!rxChart) return;
    var bins = 15; // 15 x 2min = 30min window
    var counts = new Array(bins).fill(0);
    var labels = new Array(bins);
    var now = Date.now();
    var windowMs = 30*60*1000;
    var binMs = windowMs / bins;

    for(var b=0;b<bins;b++){
      var ageStartMin = Math.round(((bins-b)*binMs)/60000);
      var ageEndMin = Math.round((((bins-b)-1)*binMs)/60000);
      labels[b] = '-' + ageStartMin + 'm';
      if (b === bins-1) labels[b] = 'now';
    }

    for(var i=0;i<events.length;i++){
      var t = Date.parse(g(events[i],'ts',''));
      if(!isFinite(t)) continue;
      var age = now - t;
      if(age < 0 || age > windowMs) continue;
      var idx = bins - 1 - Math.floor(age / binMs);
      if(idx>=0 && idx<bins) counts[idx]++;
    }

    rxChart.setOption({
      animation:false,
      grid:{left:36,right:12,top:18,bottom:24},
      xAxis:{type:'category',data:labels,axisLabel:{color:'#b6c2cf',fontSize:10},axisLine:{lineStyle:{color:'#2a3948'}}},
      yAxis:{type:'value',minInterval:1,axisLabel:{color:'#b6c2cf',fontSize:10},splitLine:{lineStyle:{color:'#2a3948'}}},
      tooltip:{trigger:'axis'},
      series:[{type:'bar',data:counts,itemStyle:{color:'#7fc8ff'},barMaxWidth:14}]
    }, true);
  }

  function computeSummary(){
    var now = Date.now(), recent=[];
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
    var f=sensor.value.trim(), de=g(ev,'decode',{});
    if(f && String(g(de,'sensor_id',''))!==f) return false;
    var st=g(ev,'status','');
    var sf=statusFilter.value; if(sf && st!==sf) return false;
    if(warnOnly.checked && st==='ok') return false;
    if(okOnly.checked && st!=='ok') return false;
    var ms=minScore.value.trim();
    if(ms){ var v=Number(ms), q=g(g(ev,'quality',{}),'score',null); if(typeof q==='number' && q < v) return false; }
    return true;
  }

  function detailPayload(evt){
    var fr=g(evt,'frame',{});
    return JSON.stringify({
      ts:g(evt,'ts',''), status:g(evt,'status',''), summary:g(evt,'summary',''),
      quality:g(evt,'quality',{}), errors:g(evt,'errors',[]), decode:g(evt,'decode',{}),
      frame:{ payload_hex:g(fr,'payload_hex',''), bits_preview:String(g(fr,'payload_bits','')).slice(0,128) }
    }, null, 2);
  }

  function clearInlineDetail(){
    if(inlineRow && inlineRow.parentNode){ inlineRow.parentNode.removeChild(inlineRow); }
    inlineRow=null;
  }

  function showDetail(tr, evt){
    var key = String(g(evt,'ts','')) + '|' + String(g(g(evt,'decode',{}),'sensor_id','')) + '|' + String(g(g(evt,'decode',{}),'data_val',''));
    if(selectedDetailKey === key){
      selectedDetailKey = '';
      clearInlineDetail();
      if(detailTop){ detailTop.style.display='none'; }
      return;
    }
    selectedDetailKey = key;

    var text=detailPayload(evt);
    if(detailMode.value==='top'){
      clearInlineDetail();
      if(detailTop){ detailTop.style.display='block'; detailText.textContent=text; }
      return;
    }
    if(detailTop){ detailTop.style.display='none'; }
    clearInlineDetail();
    inlineRow=document.createElement('tr'); inlineRow.className='inline-detail';
    var td=document.createElement('td'); td.colSpan=9;
    var pre=document.createElement('pre'); pre.textContent=text;
    td.appendChild(pre); inlineRow.appendChild(td);
    tr.parentNode.insertBefore(inlineRow, tr.nextSibling);
  }

  function renderRfNow(){
    if(!events.length) return;
    var ev = events[events.length-1] || {};
    var rx = g(ev,'rx',{});
    rfFreqNow.textContent = (rx.center_freq_hz!=null?rx.center_freq_hz:'-');
    rfGainNow.textContent = (rx.rf_gain_db!=null?rx.rf_gain_db:'-');
    rfSqNow.textContent = (rx.rf_squelch_db!=null?rx.rf_squelch_db:'-');
  }

  function loadRfConfig(){
    fetch('/api/admin/rf_control').then(function(r){return r.json();}).then(function(c){
      rfFreqSet.value = (c.center_freq_hz!=null?c.center_freq_hz:'');
      rfGainSet.value = (c.rf_gain_db!=null?c.rf_gain_db:'');
      rfSqSet.value = (c.rf_squelch_db!=null?c.rf_squelch_db:'');
    })['catch'](function(){});
  }

  function render(){
    clearInlineDetail();
    rows.innerHTML='';
    var shown=0;
    for(var i=events.length-1;i>=0;i--){
      var ev=events[i]; if(!passFilter(ev)) continue; shown++;
      var tr=document.createElement('tr'); tr.className=g(ev,'status','');
      var q=g(g(ev,'quality',{}),'score',null); q=(typeof q==='number')?q.toFixed(3):'';
      var c=g(g(ev,'quality',{}),'confidence','');
      var errs=g(ev,'errors',[]); var errN=(errs&&errs.length)?errs.length:0;
      var de=g(ev,'decode',{});
      var sid=g(de,'sensor_id','');
      var sidLink = (sid!=='' && sid!==null && sid!==undefined) ? ('<a style="color:#7fc8ff" href="/trends?sensor_id='+encodeURIComponent(String(sid))+'&window=24h">'+sid+'</a>') : '';
      tr.innerHTML='<td>'+fmtTs(g(ev,'ts',''))+'</td><td>'+g(ev,'status','')+'</td><td>'+q+'</td><td>'+c+'</td><td>'+errN+'</td><td>'+sidLink+'</td><td>'+g(de,'format_id','')+'</td><td>'+g(de,'data_val','')+'</td><td>'+g(ev,'summary','')+'</td>';
      (function(t,e){ t.addEventListener('click', function(){ showDetail(t,e); }); })(tr,ev);
      rows.appendChild(tr);
      if(shown>=300) break;
    }
    count.textContent=String(events.length);
    computeSummary();
    drawRxBars();
    renderRfNow();
  }

  function exportCSV(){
    var filtered=[]; for(var i=0;i<events.length;i++) if(passFilter(events[i])) filtered.push(events[i]);
    var lines=['"ts","status","quality_score","quality_confidence","errors_count","sensor_id","format_id","data_val","summary","error_codes"'];
    for(var j=0;j<filtered.length;j++){
      var ev=filtered[j], de=g(ev,'decode',{}), q=g(ev,'quality',{}), errs=g(ev,'errors',[]);
      var errCodes=[]; for(var k=0;k<errs.length;k++) errCodes.push(g(errs[k],'code',''));
      var row=[g(ev,'ts',''),g(ev,'status',''),g(q,'score',''),g(q,'confidence',''),errs.length||0,g(de,'sensor_id',''),g(de,'format_id',''),g(de,'data_val',''),g(ev,'summary',''),errCodes.join('|')];
      for(var r=0;r<row.length;r++) row[r]=escCSV(row[r]);
      lines.push(row.join(','));
    }
    var blob = new Blob([lines.join('\\n')], {type:'text/csv;charset=utf-8;'});
    var url = URL.createObjectURL(blob); var a=document.createElement('a'); a.href=url; a.download='fwlab_filtered_events.csv'; a.click(); URL.revokeObjectURL(url);
  }

  function resetFilters(){ sensor.value=''; minScore.value=''; statusFilter.value=''; warnOnly.checked=false; okOnly.checked=false; render(); }

  [sensor,minScore,statusFilter,warnOnly,okOnly,timeMode,detailMode].forEach(function(el){ el.addEventListener('input',render); });
  exportBtn.addEventListener('click',exportCSV);
  resetBtn.addEventListener('click',resetFilters);
  rfApply.addEventListener('click', function(){
    var body={
      center_freq_hz: rfFreqSet.value.trim()==='' ? null : Number(rfFreqSet.value),
      rf_gain_db: rfGainSet.value.trim()==='' ? null : Number(rfGainSet.value),
      rf_squelch_db: rfSqSet.value.trim()==='' ? null : Number(rfSqSet.value)
    };
    fetch('/api/admin/rf_control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      .then(function(r){return r.json();})
      .then(function(d){ rfMsg.textContent = d.ok ? ' saved (restart receiver to apply)' : ' failed'; })
      ['catch'](function(){ rfMsg.textContent=' failed'; });
  });

  function receiverAction(action){
    fetch('/api/admin/receiver_action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:action})})
      .then(function(r){return r.json();})
      .then(function(d){ rfMsg.textContent = d.ok ? (' receiver '+action+' ok') : (' receiver '+action+' failed'); })
      ['catch'](function(){ rfMsg.textContent=' receiver '+action+' failed'; });
  }
  rxStart.addEventListener('click', function(){ receiverAction('start'); });
  rxStop.addEventListener('click', function(){ receiverAction('stop'); });
  rxRestart.addEventListener('click', function(){ receiverAction('restart'); });

  fetch('/api/events?limit=400').then(function(r){return r.json();}).then(function(d){events=d.events||[]; source.textContent=g(d,'source','n/a'); render();});
  loadRfConfig();

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
  function pollReceiver(){
    fetch('/api/receiver_status').then(function(r){return r.json();}).then(function(d){
      rxState.textContent = d.state || 'unknown';
      rxState.className = (d.state==='online') ? 'good' : ((d.state==='stale') ? 'warn' : 'bad');
    })['catch'](function(){});
  }

  function pollStorage(){
    fetch('/api/storage_status').then(function(r){return r.json();}).then(function(d){
      var mode=(d.mode||'n/a');
      document.getElementById('st-mode').textContent=mode;
      document.getElementById('st-used').textContent=(d.disk_used_percent!=null?d.disk_used_percent:'-');
      document.getElementById('st-free').textContent=(d.disk_free_gb!=null?d.disk_free_gb:'-');
      document.getElementById('st-days').textContent=(d.effective_days!=null?d.effective_days:'-');
      var el=document.getElementById('st-mode');
      el.className = (mode==='emergency'||mode==='critical') ? 'bad' : (mode==='warn' ? 'warn' : 'good');
    })['catch'](function(){});
  }
  pollHost(); setInterval(pollHost,3000);
  pollReceiver(); setInterval(pollReceiver,5000);
  pollStorage(); setInterval(pollStorage,10000);

  var es=new EventSource('/api/live');
  es.onmessage=function(m){
    try{
      events.push(JSON.parse(m.data));
      if(events.length>4000) events=events.slice(-4000);
      fetch('/api/events?limit=1').then(function(r){return r.json();}).then(function(d){ source.textContent=g(d,'source','n/a'); })['catch'](function(){});
      render();
      status.textContent='live';
    }catch(e){}
  };
  es.onerror=function(){ status.textContent='reconnecting'; };
  window.addEventListener('resize', function(){ if(rxChart) rxChart.resize(); });
})();
</script></body></html>"""

ADMIN_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>FW-LAB Admin</title>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,button{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}a{color:#7fc8ff}.row{margin:.35rem 0}</style></head>
<body><div class='page'>
<h2 style='margin-top:0'>FW-LAB Admin</h2>
<div class='card'><strong>Navigation:</strong> <a href='/'>Dashboard</a> · <a href='/events'>Events</a> · <a href='/radio'>Radio</a> · <a href='/trends'>Trends</a> · <a href='/admin'>Admin</a></div>
<div class='card'>
  <div class='row'>Local retention days: <input id='localDays' type='number' step='0.1'></div>
  <div class='row'>Max local MB: <input id='maxMb' type='number' step='1'></div>
  <div class='row'>Warn disk %: <input id='warnPct' type='number' step='0.1'></div>
  <div class='row'>Critical disk %: <input id='critPct' type='number' step='0.1'></div>
  <div class='row'>Emergency disk %: <input id='emerPct' type='number' step='0.1'></div>
  <div class='row'>Critical retention days: <input id='critDays' type='number' step='0.1'></div>
  <div class='row'>Emergency retention hours: <input id='emerHours' type='number' step='1'></div>
  <button id='save'>Save policy</button> <span id='msg'></span>
</div>
<script>
(function(){
  function setv(id,v){ document.getElementById(id).value = (v==null?'':v); }
  function num(id){ var x=parseFloat(document.getElementById(id).value); return isNaN(x)?null:x; }
  function load(){
    fetch('/api/admin/storage_policy').then(r=>r.json()).then(p=>{
      setv('localDays', p.localRetentionDays); setv('maxMb', p.maxLocalMb);
      setv('warnPct', p.thresholds?.warnDiskPercent); setv('critPct', p.thresholds?.criticalDiskPercent); setv('emerPct', p.thresholds?.emergencyDiskPercent);
      setv('critDays', p.criticalPolicy?.criticalRetentionDays); setv('emerHours', p.criticalPolicy?.emergencyRetentionHours);
    });
  }
  document.getElementById('save').addEventListener('click', function(){
    var body={
      localRetentionDays:num('localDays'),
      maxLocalMb:num('maxMb'),
      thresholds:{warnDiskPercent:num('warnPct'),criticalDiskPercent:num('critPct'),emergencyDiskPercent:num('emerPct')},
      criticalPolicy:{criticalRetentionDays:num('critDays'),emergencyRetentionHours:num('emerHours')}
    };
    fetch('/api/admin/storage_policy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json()).then(d=>{ document.getElementById('msg').textContent = d.ok ? ' saved' : ' failed'; });
  });
  load();
})();
</script></div></body></html>"""

TRENDS_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>FW-LAB Trends</title>
<script src='https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'></script>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,select,button{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}a{color:#7fc8ff}#chart{height:420px}</style></head>
<body><div class='page'>
<h2 style='margin-top:0'>FW-LAB Sensor Trends</h2>
<div class='card'><strong>Navigation:</strong> <a href='/'>Dashboard</a> · <a href='/events'>Events</a> · <a href='/radio'>Radio</a> · <a href='/trends'>Trends</a> · <a href='/admin'>Admin</a><br><br>
Sensor ID: <input id='sensor' list='sensorList' style='width:120px' placeholder='e.g. 4099'>
<datalist id='sensorList'></datalist>
<button id='refreshSensors'>Sensors</button>
Window: <select id='window'><option value='15m'>15m</option><option value='1h'>1h</option><option value='6h'>6h</option><option value='24h' selected>24h</option></select>
Source: <select id='sourceMode'><option value='local' selected>local</option><option value='archive'>archive</option></select>
Metric: <select id='metricMode'><option value='raw' selected>raw</option><option value='delta'>delta</option><option value='ror'>rate/min</option></select>
Threshold ≥ <input id='threshold' style='width:90px' placeholder='off'>
Time: <select id='timeMode'><option value='local' selected>local</option><option value='zulu'>zulu</option></select>
Y Min: <input id='ymin' style='width:90px' placeholder='auto'>
Y Max: <input id='ymax' style='width:90px' placeholder='auto'>
<button id='load'>Load</button> <button id='resetZoom'>Reset zoom</button>
View name <input id='viewName' style='width:120px' placeholder='optional'>
<button id='saveView'>Save view</button>
<select id='savedViews'><option value=''>saved views</option></select>
<span id='msg'></span></div>
<div class='card'>Latest: <span id='latest'>-</span> · Min: <span id='min'>-</span> · Max: <span id='max'>-</span> · Avg: <span id='avg'>-</span></div>
<div class='card'><div id='chart'></div></div>
<script>
(function(){
  var sensor=document.getElementById('sensor'), win=document.getElementById('window'), sourceMode=document.getElementById('sourceMode'), metricMode=document.getElementById('metricMode'), threshold=document.getElementById('threshold'), timeMode=document.getElementById('timeMode'), msg=document.getElementById('msg');
  var sensorList=document.getElementById('sensorList'), refreshSensors=document.getElementById('refreshSensors');
  var viewName=document.getElementById('viewName'), saveView=document.getElementById('saveView'), savedViews=document.getElementById('savedViews');
  var ymin=document.getElementById('ymin'), ymax=document.getElementById('ymax');
  var latest=document.getElementById('latest'), minv=document.getElementById('min'), maxv=document.getElementById('max'), avgv=document.getElementById('avg');
  var chart = echarts.init(document.getElementById('chart'));
  var lastPoints=[];

  function fmt(ts){ var d=new Date(ts); if(!isFinite(d.getTime())) return ts; return timeMode.value==='zulu' ? d.toISOString() : d.toLocaleString(); }

  function draw(points){
    lastPoints = points || [];
    var data = lastPoints.map(function(p){ return [fmt(p.ts), p.value]; });
    var yMin = ymin.value.trim(); var yMax = ymax.value.trim();
    var option = {
      backgroundColor:'#17212b',
      animation:false,
      tooltip:{trigger:'axis'},
      toolbox:{feature:{dataZoom:{yAxisIndex:'none'},restore:{},saveAsImage:{}}},
      xAxis:{type:'category',boundaryGap:false,data:data.map(function(x){return x[0];}),axisLabel:{color:'#d7e0ea'},axisLine:{lineStyle:{color:'#2a3948'}}},
      yAxis:{type:'value',min: yMin===''? null : Number(yMin), max: yMax===''? null : Number(yMax),axisLabel:{color:'#d7e0ea'},splitLine:{lineStyle:{color:'#2a3948'}}},
      dataZoom:[{type:'inside',xAxisIndex:0,filterMode:'none'},{type:'slider',xAxisIndex:0,filterMode:'none'}],
      series:[{name:'data_val',type:'line',showSymbol:false,smooth:0.15,lineStyle:{width:1.8,color:'#7fc8ff'},areaStyle:{color:'rgba(127,200,255,.18)'},data:data.map(function(x){return x[1];})}]
    };
    chart.setOption(option,true);
  }

  function load(){ var sid=sensor.value.trim(); if(!sid){ msg.textContent=' enter sensor id'; return; } msg.textContent=' loading...';
    var thr = threshold.value.trim();
    var q = '/api/trends?sensor_id='+encodeURIComponent(sid)+'&window='+encodeURIComponent(win.value)+'&source='+encodeURIComponent(sourceMode.value)+'&metric='+encodeURIComponent(metricMode.value)+'&limit=12000';
    if(thr!=='') q += '&threshold=' + encodeURIComponent(thr);
    fetch(q).then(function(r){return r.json();}).then(function(d){
      var pts = d.points||[];
      msg.textContent=' source='+ (d.source_mode||sourceMode.value) +' metric='+ (d.metric||metricMode.value) +' points='+pts.length;
      latest.textContent=(d.stats && d.stats.latest!=null)?d.stats.latest:'-';
      minv.textContent=(d.stats && d.stats.min!=null)?d.stats.min:'-';
      maxv.textContent=(d.stats && d.stats.max!=null)?d.stats.max:'-';
      avgv.textContent=(d.stats && d.stats.avg!=null)?d.stats.avg:'-';
      draw(pts);
    }).catch(function(){ msg.textContent=' failed'; draw([]); }); }

  function loadSensors(){
    fetch('/api/sensors?source='+encodeURIComponent(sourceMode.value)).then(function(r){return r.json();}).then(function(d){
      var ids=d.sensor_ids||[];
      sensorList.innerHTML='';
      ids.forEach(function(id){ var o=document.createElement('option'); o.value=String(id); sensorList.appendChild(o); });
      msg.textContent=' sensors='+ids.length;
    })['catch'](function(){});
  }

  function loadSavedViews(){
    fetch('/api/views').then(function(r){return r.json();}).then(function(d){
      var views=d.views||[];
      savedViews.innerHTML='<option value="">saved views</option>';
      views.forEach(function(v){
        var o=document.createElement('option');
        o.value=JSON.stringify(v);
        o.textContent=v.name || ('view-'+v.id);
        savedViews.appendChild(o);
      });
    })['catch'](function(){});
  }

  function applyView(v){
    if(!v) return;
    sensor.value = v.sensor_id || '';
    if(v.window) win.value = v.window;
    if(v.source) sourceMode.value = v.source;
    if(v.metric) metricMode.value = v.metric;
    threshold.value = (v.threshold==null?'':v.threshold);
    loadSensors();
    if(sensor.value.trim()) load();
  }

  document.getElementById('load').addEventListener('click',load);
  document.getElementById('resetZoom').addEventListener('click',function(){ draw(lastPoints); });
  timeMode.addEventListener('input',function(){ draw(lastPoints); });
  sourceMode.addEventListener('input',function(){ loadSensors(); });
  refreshSensors.addEventListener('click',function(){ loadSensors(); });
  ymin.addEventListener('change',function(){ draw(lastPoints); });
  ymax.addEventListener('change',function(){ draw(lastPoints); });
  savedViews.addEventListener('change', function(){
    if(!savedViews.value) return;
    try{ applyView(JSON.parse(savedViews.value)); }catch(e){}
  });
  saveView.addEventListener('click', function(){
    var body={
      name: viewName.value.trim() || ('view-'+Date.now()),
      sensor_id: sensor.value.trim(),
      window: win.value,
      source: sourceMode.value,
      metric: metricMode.value,
      threshold: threshold.value.trim()==='' ? null : Number(threshold.value)
    };
    fetch('/api/views',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      .then(function(r){return r.json();})
      .then(function(d){ msg.textContent = d.ok ? ' view saved' : ' save failed'; loadSavedViews(); })
      ['catch'](function(){ msg.textContent=' save failed'; });
  });

  var params = new URLSearchParams(window.location.search);
  var qpSensor = params.get('sensor_id');
  var qpWindow = params.get('window');
  var qpSource = params.get('source');
  var qpMetric = params.get('metric');
  var qpThreshold = params.get('threshold');
  if(qpSensor){ sensor.value = qpSensor; }
  if(qpWindow && ['15m','1h','6h','24h'].indexOf(qpWindow) >= 0){ win.value = qpWindow; }
  if(qpSource && ['local','archive'].indexOf(qpSource) >= 0){ sourceMode.value = qpSource; }
  if(qpMetric && ['raw','delta','ror'].indexOf(qpMetric) >= 0){ metricMode.value = qpMetric; }
  if(qpThreshold){ threshold.value = qpThreshold; }
  loadSensors();
  loadSavedViews();
  if(sensor.value.trim()){ load(); }
  window.addEventListener('resize', function(){ chart.resize(); });
})();
</script></div></body></html>"""

RADIO_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>FW-LAB Radio</title>
<style>
body{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#0f141a;color:#e6edf3;margin:0}
.wrap{max-width:1200px;margin:0 auto;padding:1rem}
.card{background:#17212b;border:1px solid #243243;border-radius:10px;padding:.8rem;margin:.6rem 0}
.row{display:flex;gap:1rem;flex-wrap:wrap}
.kpi{min-width:180px}.muted{color:#9fb0c3}.good{color:#6dd17c}.warn{color:#f2c14e}.bad{color:#f36f6f}
pre{margin:0;white-space:pre-wrap;word-break:break-word;font-size:.86rem}
</style>
<script src='https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'></script></head><body><div class='wrap'>
  <div class='card'><strong>Navigation:</strong> <a href='/' style='color:#7fc8ff'>Dashboard</a> · <a href='/events' style='color:#7fc8ff'>Events</a> · <a href='/radio' style='color:#7fc8ff'>Radio</a> · <a href='/trends' style='color:#7fc8ff'>Trends</a> · <a href='/admin' style='color:#7fc8ff'>Admin</a></div>
  <div class='card'><strong>Radio Live</strong> <span class='muted'>· Real-time RF/decode health</span></div>
  <div class='row'>
    <div class='card kpi'>Receiver<br><strong id='rx'>unknown</strong></div>
    <div class='card kpi'>Events/min<br><strong id='rate'>0.0</strong></div>
    <div class='card kpi'>Ones ratio avg<br><strong id='ones'>n/a</strong></div>
    <div class='card kpi'>Top error<br><strong id='toperr'>none</strong></div>
  </div>
  <div class='card'><div id='chart' style='height:220px'></div></div>
  <div class='card'><strong>Latest symbol waveform (post symbol-sync)</strong><div id='symchart' style='height:220px'></div></div>
  <div class='card'><strong>Recent error codes</strong><pre id='errs'>none</pre></div>
</div>
<script>
(function(){
  function g(o,k,d){return (o&&o[k]!==undefined&&o[k]!==null)?o[k]:d;}
  var events=[]; var max=1200;
  var rx=document.getElementById('rx'), rate=document.getElementById('rate'), ones=document.getElementById('ones'), toperr=document.getElementById('toperr'), errs=document.getElementById('errs');
  var chart=(window.echarts)?echarts.init(document.getElementById('chart')):null;
  var symchart=(window.echarts)?echarts.init(document.getElementById('symchart')):null;

  function refresh(){
    if(!events.length) return;
    var now=Date.now();
    var recent=events.filter(function(e){var t=Date.parse(g(e,'ts','')); return isFinite(t) && (now-t)<=300000;});
    rate.textContent=(recent.length/5.0).toFixed(2);

    var rs={}, sum=0, n=0, ec={};
    recent.forEach(function(e){
      rs[g(e,'status','ok')] = (rs[g(e,'status','ok')]||0)+1;
      var q=g(e,'quality',{}), or=g(q,'ones_ratio',null); if(typeof or==='number'){sum+=or;n++;}
      (g(e,'errors',[])||[]).forEach(function(er){ var c=g(er,'code','unknown'); ec[c]=(ec[c]||0)+1; });
    });
    var st=(rs.error>0)?'error':((rs.warn>0)?'warn':'ok');
    rx.textContent=st.toUpperCase()+' (ok:'+(rs.ok||0)+' warn:'+(rs.warn||0)+' err:'+(rs.error||0)+')';
    rx.className=st==='ok'?'good':(st==='warn'?'warn':'bad');
    ones.textContent=n? (sum/n).toFixed(3) : 'n/a';

    var top='none', topn=0; Object.keys(ec).forEach(function(k){ if(ec[k]>topn){topn=ec[k]; top=k;} });
    toperr.textContent=topn? (top+' ('+topn+')') : 'none';
    errs.textContent=Object.keys(ec).sort(function(a,b){return ec[b]-ec[a];}).slice(0,10).map(function(k){return k+': '+ec[k];}).join('\n') || 'none';

    if(chart){
      var tail=events.slice(-200), xs=[], ys=[];
      tail.forEach(function(e){ var t=Date.parse(g(e,'ts','')); var q=g(e,'quality',{}), or=g(q,'ones_ratio',null); if(isFinite(t) && typeof or==='number'){ xs.push(new Date(t).toLocaleTimeString()); ys.push(or);} });
      chart.setOption({animation:false,grid:{left:40,right:12,top:20,bottom:28},xAxis:{type:'category',data:xs},yAxis:{type:'value',min:0,max:1},tooltip:{trigger:'axis'},series:[{type:'line',data:ys,symbol:'none'}]});
    }

    if(symchart){
      var sym=[];
      for(var i=events.length-1;i>=0;i--){
        var fr=g(events[i],'frame',{}), s=g(fr,'symbol_samples',null);
        if(s && s.length){ sym=s; break; }
      }
      var sx=[], sy=[];
      for(var j=0;j<sym.length;j++){ sx.push(String(j)); sy.push(Number(sym[j])); }
      symchart.setOption({animation:false,grid:{left:40,right:12,top:20,bottom:28},xAxis:{type:'category',data:sx},yAxis:{type:'value',min:-2,max:2},tooltip:{trigger:'axis'},series:[{type:'line',data:sy,symbol:'none',step:'middle'}]});
    }
  }

  fetch('/api/events?limit=800').then(function(r){return r.json();}).then(function(d){ events=d.events||[]; refresh(); });
  var es=new EventSource('/api/stream');
  es.onmessage=function(m){ try{ events.push(JSON.parse(m.data)); if(events.length>max) events=events.slice(-max); refresh(); }catch(e){} };
  window.addEventListener('resize', function(){ if(chart) chart.resize(); if(symchart) symchart.resize(); });
})();
</script></body></html>"""


def load_access_policy(path='config/access_policy.json'):
    p = Path(path)
    if not p.exists():
        return {'adminApi': {'enabled': False, 'token': '', 'allowLocalhostWithoutToken': True}}
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        admin = d.get('adminApi') or {}
        return {
            'adminApi': {
                'enabled': bool(admin.get('enabled', False)),
                'token': str(admin.get('token', '')),
                'allowLocalhostWithoutToken': bool(admin.get('allowLocalhostWithoutToken', True)),
            }
        }
    except Exception:
        return {'adminApi': {'enabled': False, 'token': '', 'allowLocalhostWithoutToken': True}}


def audit_admin_action(action: str, remote_addr: str, ok: bool, details: dict | None = None):
    out = Path('rf_log/audit/admin_actions.jsonl')
    out.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        'ts': datetime.utcnow().isoformat() + 'Z',
        'action': action,
        'remote_addr': remote_addr,
        'ok': bool(ok),
        'details': details or {},
    }
    with out.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec) + '\n')


def is_local_request(remote_addr: str) -> bool:
    ra = (remote_addr or '').split(':')[0]
    return ra in ('127.0.0.1', '::1', 'localhost')


def admin_authorized(headers, remote_addr: str):
    pol = load_access_policy().get('adminApi', {})
    if not pol.get('enabled', False):
        return True
    if pol.get('allowLocalhostWithoutToken', True) and is_local_request(remote_addr):
        return True
    token = str(pol.get('token', ''))
    supplied = headers.get('X-Admin-Token', '')
    return bool(token) and (supplied == token)


def load_rf_control(path='config/rf_control.json'):
    p = Path(path)
    if not p.exists():
        return {'center_freq_hz': 173900000.0, 'rf_gain_db': 40.0, 'rf_squelch_db': -33.0}
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        return {
            'center_freq_hz': d.get('center_freq_hz', 173900000.0),
            'rf_gain_db': d.get('rf_gain_db', -1.0),
            'rf_squelch_db': d.get('rf_squelch_db', -33.0),
        }
    except Exception:
        return {'center_freq_hz': 173900000.0, 'rf_gain_db': 40.0, 'rf_squelch_db': -33.0}


def save_rf_control(cfg: dict, path='config/rf_control.json'):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2) + '\n', encoding='utf-8')


def load_storage_policy(path='config/storage_policy.json'):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_storage_policy(policy: dict, path='config/storage_policy.json'):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(policy, indent=2) + '\n', encoding='utf-8')


def storage_status():
    pol = load_storage_policy()
    th = pol.get('thresholds', {})
    warn = float(th.get('warnDiskPercent', 85))
    critical = float(th.get('criticalDiskPercent', 92))
    emergency = float(th.get('emergencyDiskPercent', 96))

    cp = pol.get('criticalPolicy', {})
    local_days = float(pol.get('localRetentionDays', 2))
    critical_days = float(cp.get('criticalRetentionDays', 1))
    emergency_hours = float(cp.get('emergencyRetentionHours', 12))

    d = shutil.disk_usage('/')
    used_pct = (100.0 * d.used / d.total) if d.total else 0.0
    mode = 'normal'
    effective_days = local_days
    if used_pct >= emergency:
        mode = 'emergency'
        effective_days = emergency_hours / 24.0
    elif used_pct >= critical:
        mode = 'critical'
        effective_days = critical_days
    elif used_pct >= warn:
        mode = 'warn'

    return {
        'mode': mode,
        'disk_used_percent': round(used_pct, 3),
        'disk_free_gb': round(d.free / (1024**3), 3),
        'effective_days': round(effective_days, 3),
        'policy_days': local_days,
    }


def receiver_status(store: 'EventStore'):
    running = False
    try:
        out = subprocess.check_output("pgrep -af 'python3 .*ALERT1v3.py'", shell=True, text=True)
        running = bool(out.strip())
    except Exception:
        running = False

    state = 'offline'
    last_ts = None
    age_s = None
    if store and store.events:
        ev = store.events[-1]
        last_ts = ev.get('ts')
        dt = parse_ts(last_ts) if last_ts else None
        if dt:
            age_s = (time.time() - dt.timestamp())

    if running:
        if age_s is None:
            state = 'online'
        elif age_s <= 20:
            state = 'online'
        elif age_s <= 120:
            state = 'stale'
        else:
            state = 'online_no_data'

    return {'state': state, 'running': running, 'last_event_ts': last_ts, 'last_event_age_s': round(age_s,3) if age_s is not None else None}


def parse_ts(ts: str):
    try:
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def window_seconds(w: str) -> int:
    return {'15m': 900, '1h': 3600, '6h': 21600, '24h': 86400}.get(w, 3600)


def load_saved_views(path='config/saved_views.json'):
    p = Path(path)
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        return d.get('views', []) if isinstance(d, dict) else []
    except Exception:
        return []


def save_saved_views(views, path='config/saved_views.json'):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({'views': views}, indent=2) + '\n', encoding='utf-8')


def apply_metric(points, metric: str, threshold):
    metric = (metric or 'raw').lower()
    if metric == 'raw':
        out = points
    elif metric == 'delta':
        out = []
        prev = None
        for p in points:
            if prev is None:
                prev = p
                continue
            out.append({'ts': p['ts'], 'value': p['value'] - prev['value']})
            prev = p
    elif metric == 'ror':
        out = []
        prev = None
        for p in points:
            if prev is None:
                prev = p
                continue
            dt1 = parse_ts(prev['ts'])
            dt2 = parse_ts(p['ts'])
            if not dt1 or not dt2:
                prev = p
                continue
            mins = (dt2.timestamp() - dt1.timestamp()) / 60.0
            if mins <= 0:
                prev = p
                continue
            out.append({'ts': p['ts'], 'value': (p['value'] - prev['value']) / mins})
            prev = p
    else:
        out = points

    if threshold is None:
        return out
    try:
        t = float(threshold)
        out = [p for p in out if p['value'] >= t]
    except Exception:
        pass
    return out


def _archive_manifest(path='rf_log/archive_state/manifest.json'):
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return data.get('entries', []) if isinstance(data, dict) else []
    except Exception:
        return []


def sensor_ids_from_archive(limit_entries: int = 200):
    ids = set()
    entries = [e for e in _archive_manifest() if e.get('status') == 'uploaded' and e.get('chunk_path')]
    for ent in entries[-max(1, limit_entries):]:
        cp = Path(ent.get('chunk_path'))
        if not cp.exists():
            continue
        try:
            with gzip.open(cp, 'rt', encoding='utf-8', errors='replace') as gz:
                for line in gz:
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    de = ev.get('decode') or {}
                    sid = de.get('sensor_id')
                    if sid is not None:
                        ids.add(str(sid))
        except Exception:
            continue
    return sorted(ids)


def trends_from_archive(sensor_id: str, win: str, limit: int):
    cutoff = time.time() - window_seconds(win)
    entries = [e for e in _archive_manifest() if e.get('status') == 'uploaded' and e.get('chunk_path')]
    entries = sorted(entries, key=lambda e: e.get('first_ts') or '')

    points = []
    src = 'archive:none'
    for ent in entries:
        cp = Path(ent.get('chunk_path'))
        if not cp.exists():
            continue
        src = str(cp)
        try:
            with gzip.open(cp, 'rt', encoding='utf-8', errors='replace') as gz:
                for line in gz:
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    de = ev.get('decode') or {}
                    if str(de.get('sensor_id', '')) != sensor_id:
                        continue
                    ts = ev.get('ts', '')
                    dt = parse_ts(ts)
                    if not dt or dt.timestamp() < cutoff:
                        continue
                    v = de.get('data_val')
                    if isinstance(v, (int, float)):
                        points.append({'ts': ts, 'value': float(v)})
        except Exception:
            continue

    points = sorted(points, key=lambda p: p['ts'])[-limit:]
    vals = [p['value'] for p in points]
    stats = {
        'latest': vals[-1] if vals else None,
        'min': min(vals) if vals else None,
        'max': max(vals) if vals else None,
        'avg': round(sum(vals)/len(vals), 3) if vals else None,
    }
    return {'points': points, 'stats': stats, 'source': src}


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

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/views':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(length) if length > 0 else b'{}'
                body = json.loads(raw.decode('utf-8'))
                if not isinstance(body, dict):
                    raise ValueError('body must be object')
                views = load_saved_views()
                view = {
                    'id': int(time.time() * 1000),
                    'name': str(body.get('name', 'view')).strip() or 'view',
                    'sensor_id': str(body.get('sensor_id', '')).strip(),
                    'window': str(body.get('window', '24h')),
                    'source': str(body.get('source', 'local')),
                    'metric': str(body.get('metric', 'raw')),
                    'threshold': body.get('threshold', None),
                }
                views.append(view)
                save_saved_views(views)
                return self._json({'ok': True, 'view': view})
            except Exception as e:
                return self._json({'ok': False, 'error': str(e)}, code=400)

        if parsed.path in ['/api/admin/storage_policy', '/api/admin/rf_control', '/api/admin/receiver_action']:
            if not admin_authorized(self.headers, self.client_address[0] if self.client_address else ''):
                audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', False, {'error': 'unauthorized'})
                return self._json({'ok': False, 'error': 'unauthorized'}, code=403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(length) if length > 0 else b'{}'
                body = json.loads(raw.decode('utf-8'))
                if not isinstance(body, dict):
                    raise ValueError('body must be object')

                if parsed.path == '/api/admin/storage_policy':
                    current = load_storage_policy()
                    merged = {
                        'localRetentionDays': body.get('localRetentionDays', current.get('localRetentionDays', 2)),
                        'maxLocalMb': body.get('maxLocalMb', current.get('maxLocalMb', 1024)),
                        'thresholds': {
                            'warnDiskPercent': (body.get('thresholds') or {}).get('warnDiskPercent', (current.get('thresholds') or {}).get('warnDiskPercent', 85)),
                            'criticalDiskPercent': (body.get('thresholds') or {}).get('criticalDiskPercent', (current.get('thresholds') or {}).get('criticalDiskPercent', 92)),
                            'emergencyDiskPercent': (body.get('thresholds') or {}).get('emergencyDiskPercent', (current.get('thresholds') or {}).get('emergencyDiskPercent', 96)),
                        },
                        'criticalPolicy': {
                            'criticalRetentionDays': (body.get('criticalPolicy') or {}).get('criticalRetentionDays', (current.get('criticalPolicy') or {}).get('criticalRetentionDays', 1)),
                            'emergencyRetentionHours': (body.get('criticalPolicy') or {}).get('emergencyRetentionHours', (current.get('criticalPolicy') or {}).get('emergencyRetentionHours', 12)),
                        },
                    }
                    save_storage_policy(merged)
                    audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', True, {'keys': ['storage_policy']})
                    return self._json({'ok': True, 'policy': merged})

                if parsed.path == '/api/admin/rf_control':
                    current = load_rf_control()
                    merged = {
                        'center_freq_hz': body.get('center_freq_hz', current.get('center_freq_hz', 173900000.0)),
                        'rf_gain_db': body.get('rf_gain_db', current.get('rf_gain_db', 40.0)),
                        'rf_squelch_db': body.get('rf_squelch_db', current.get('rf_squelch_db', -33.0)),
                    }
                    save_rf_control(merged)
                    audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', True, {'keys': ['rf_control']})
                    return self._json({'ok': True, 'rf_control': merged})

                action = str(body.get('action', '')).strip().lower()
                if action not in ('start', 'stop', 'restart'):
                    return self._json({'ok': False, 'error': 'invalid action'}, code=400)
                cp = subprocess.run(['sudo', 'systemctl', action, 'fwlab-receiver.service'], capture_output=True, text=True)
                if cp.returncode != 0:
                    audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', False, {'action': action, 'error': cp.stderr.strip() or cp.stdout.strip()})
                    return self._json({'ok': False, 'error': cp.stderr.strip() or cp.stdout.strip()}, code=500)
                audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', True, {'action': action})
                return self._json({'ok': True, 'action': action})
            except Exception as e:
                audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', False, {'error': str(e)})
                return self._json({'ok': False, 'error': str(e)}, code=400)

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ['/', '/events']:
            payload = HTML.encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/trends':
            payload = TRENDS_HTML.encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/radio':
            payload = RADIO_HTML.encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/admin':
            payload = ADMIN_HTML.encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/api/admin/storage_policy':
            if not admin_authorized(self.headers, self.client_address[0] if self.client_address else ''):
                return self._json({'ok': False, 'error': 'unauthorized'}, code=403)
            return self._json(load_storage_policy())

        if parsed.path == '/api/admin/rf_control':
            if not admin_authorized(self.headers, self.client_address[0] if self.client_address else ''):
                return self._json({'ok': False, 'error': 'unauthorized'}, code=403)
            return self._json(load_rf_control())

        if parsed.path == '/api/admin/audit_recent':
            if not admin_authorized(self.headers, self.client_address[0] if self.client_address else ''):
                return self._json({'ok': False, 'error': 'unauthorized'}, code=403)
            q = parse_qs(parsed.query)
            limit = int(q.get('limit', ['100'])[0])
            limit = max(1, min(limit, 500))
            p = Path('rf_log/audit/admin_actions.jsonl')
            rows = []
            if p.exists():
                for line in p.read_text(encoding='utf-8', errors='replace').splitlines()[-limit:]:
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
            return self._json({'events': rows, 'count': len(rows)})

        if parsed.path == '/api/events':
            q = parse_qs(parsed.query)
            limit = int(q.get('limit', ['100'])[0])
            limit = max(1, min(limit, 4000))
            self.store.poll_new()
            events = list(self.store.events)[-limit:]
            return self._json({'events': events, 'count': len(self.store.events), 'source': str(self.store.path)})

        if parsed.path == '/api/sensors':
            q = parse_qs(parsed.query)
            source_mode = (q.get('source', ['local'])[0] or 'local').strip().lower()
            if source_mode == 'archive':
                return self._json({'source_mode': 'archive', 'sensor_ids': sensor_ids_from_archive()})

            self.store.poll_new()
            ids = set()
            for ev in list(self.store.events):
                de = ev.get('decode') or {}
                sid = de.get('sensor_id')
                if sid is not None:
                    ids.add(str(sid))
            return self._json({'source_mode': 'local', 'sensor_ids': sorted(ids)})

        if parsed.path == '/api/views':
            return self._json({'views': load_saved_views()})

        if parsed.path == '/api/trends':
            q = parse_qs(parsed.query)
            sensor_id = (q.get('sensor_id', [''])[0] or '').strip()
            win = q.get('window', ['24h'])[0]
            source_mode = (q.get('source', ['local'])[0] or 'local').strip().lower()
            metric = (q.get('metric', ['raw'])[0] or 'raw').strip().lower()
            threshold = q.get('threshold', [None])[0]
            limit = int(q.get('limit', ['2000'])[0])
            limit = max(100, min(limit, 10000))

            if source_mode == 'archive':
                res = trends_from_archive(sensor_id, win, limit)
                points = apply_metric(res['points'], metric, threshold)
                vals = [p['value'] for p in points]
                stats = {
                    'latest': vals[-1] if vals else None,
                    'min': min(vals) if vals else None,
                    'max': max(vals) if vals else None,
                    'avg': round(sum(vals)/len(vals), 3) if vals else None,
                }
                return self._json({'sensor_id': sensor_id, 'window': win, 'source_mode': 'archive', 'metric': metric, 'points': points, 'stats': stats, 'source': res['source']})

            self.store.poll_new()
            cutoff = time.time() - window_seconds(win)
            points = []
            for ev in list(self.store.events):
                de = ev.get('decode') or {}
                if str(de.get('sensor_id', '')) != sensor_id:
                    continue
                ts = ev.get('ts', '')
                dt = parse_ts(ts)
                if not dt or dt.timestamp() < cutoff:
                    continue
                v = de.get('data_val')
                if isinstance(v, (int, float)):
                    points.append({'ts': ts, 'value': float(v)})

            points = points[-limit:]
            points = apply_metric(points, metric, threshold)
            vals = [p['value'] for p in points]
            stats = {
                'latest': vals[-1] if vals else None,
                'min': min(vals) if vals else None,
                'max': max(vals) if vals else None,
                'avg': round(sum(vals)/len(vals), 3) if vals else None,
            }
            return self._json({'sensor_id': sensor_id, 'window': win, 'source_mode': 'local', 'metric': metric, 'points': points, 'stats': stats, 'source': str(self.store.path)})

        if parsed.path == '/api/storage_status':
            return self._json(storage_status())

        if parsed.path == '/api/receiver_status':
            self.store.poll_new()
            return self._json(receiver_status(self.store))

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
    if args.jsonl_follow_dir:
        print(f'Following latest in: {args.jsonl_follow_dir}')
    if args.host_metrics_jsonl:
        print(f'Host metrics source: {args.host_metrics_jsonl}')
    server.serve_forever()


if __name__ == '__main__':
    main()
