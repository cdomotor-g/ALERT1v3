#!/usr/bin/env python3
import argparse
import json
import gzip
import time
import shutil
import subprocess
import html
import os
import re
import yaml
from datetime import datetime
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

def _build_stamp():
    sha = os.environ.get('FWLAB_BUILD', '').strip()
    if not sha:
        try:
            cp = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, check=False)
            sha = (cp.stdout or '').strip() or 'dev'
        except Exception:
            sha = 'dev'
    return sha[:12]

BUILD_STAMP = _build_stamp()
RX_AGG_JSON_PATH = Path('rf_log/rx_agg.json')
NAV_HTML = f"""
<style>
:root{{--sidebar-w:212px;--sidebar-w-c:64px;--content-gap:14px;}}
.fw-shell{{display:flex;gap:0;}}
.fw-sidebar{{position:fixed;left:0;top:0;bottom:0;width:var(--sidebar-w);background:#0d131a;border-right:1px solid #243243;padding:.75rem .55rem;z-index:120;transition:width .18s ease;overflow:hidden;}}
.fw-sidebar.collapsed{{width:var(--sidebar-w-c);}}
.fw-brand{{display:flex;align-items:center;justify-content:space-between;color:#cfe2f5;font-weight:700;padding:.35rem .4rem .65rem .4rem;}}
.fw-build{{font-size:.78rem;color:#8ea6bf;}}
.fw-nav a{{display:flex;align-items:center;gap:.55rem;color:#d7e5f3;text-decoration:none;padding:.55rem .55rem;border-radius:8px;margin:.15rem 0;}}
.fw-nav a:hover{{background:#15212d;}}
.fw-nav a.active{{background:#1e2f40;color:#8fd1ff;}}
.fw-ico{{width:1.15rem;display:inline-flex;justify-content:center;}}
.fw-label{{white-space:nowrap;}}
.fw-sidebar.collapsed .fw-label{{display:none;}}
.fw-toggle{{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:6px;padding:.2rem .5rem;cursor:pointer;}}
.fw-mobilebar{{display:none;position:sticky;top:0;z-index:110;background:#0f141a;border-bottom:1px solid #243243;padding:.45rem .6rem;align-items:center;gap:.6rem;}}
.fw-main{{margin-left:calc(var(--sidebar-w) + var(--content-gap));width:calc(100% - var(--sidebar-w) - var(--content-gap));padding-left:.9rem;padding-right:.7rem;transition:margin-left .18s ease,width .18s ease;box-sizing:border-box;}}
.fw-main.nav-collapsed{{margin-left:calc(var(--sidebar-w-c) + var(--content-gap));width:calc(100% - var(--sidebar-w-c) - var(--content-gap));}}
/* visual consistency tokens applied across pages */
body{{color:#d7e5f3;letter-spacing:.1px;}}
.card{{border:1px solid #243243;border-radius:10px;box-shadow:0 1px 0 rgba(255,255,255,.02),0 8px 24px rgba(0,0,0,.18);}}
button{{background:#111a23;border:1px solid #2b3e52;color:#dce8f5;border-radius:8px;padding:.38rem .62rem;}}
button:hover{{background:#162433;}}
input,select{{background:#0e151e;border:1px solid #2a3948;color:#dce8f5;border-radius:8px;padding:.35rem .5rem;}}
h2{{font-weight:650;letter-spacing:.2px;}}
.muted{{color:#9fb0c3;}}
@media (max-width: 860px){{
  body{{font-size:15px;}}
  .fw-mobilebar{{display:flex;}}
  .fw-sidebar{{transform:translateX(-100%);width:var(--sidebar-w);}}
  .fw-sidebar.open{{transform:translateX(0);}}
  .fw-main,.fw-main.nav-collapsed{{margin-left:0;width:100%;padding-left:.6rem;padding-right:.6rem;}}
  .card{{padding:.95rem !important;}}
  input,select,button{{min-height:40px;font-size:16px;}}
  .grid{{grid-template-columns:1fr !important;gap:.5rem !important;}}
  .row{{flex-direction:column !important;}}
  .sticky-wrap{{position:static !important;}}
  #table-controls-card{{line-height:2.0;}}
  #table-controls-card input,#table-controls-card select,#table-controls-card button{{display:inline-block;margin:.15rem 0;max-width:100%;}}
  .table-wrap{{max-height:none !important;overflow:auto;-webkit-overflow-scrolling:touch;border-radius:10px;}}
  th,td{{padding:.55rem .45rem !important;white-space:nowrap;}}
  /* Events table mobile simplification */
  #rows td:nth-child(3), #rows td:nth-child(4), #rows td:nth-child(5),
  table thead th:nth-child(3), table thead th:nth-child(4), table thead th:nth-child(5){{display:none;}}
  #detailTop{{position:fixed !important;left:.4rem;right:.4rem;bottom:.4rem;z-index:140;max-height:46vh;overflow:auto;box-shadow:0 8px 30px rgba(0,0,0,.45);}}
  pre{{max-height:42vh !important;}}
}}
</style>
<div class='fw-mobilebar'><button class='fw-toggle' id='fwMobileToggle'>☰</button><strong>FW-LAB</strong><span class='fw-build'>build {BUILD_STAMP}</span></div>
<div class='fw-shell'>
  <aside class='fw-sidebar' id='fwSidebar'>
    <div class='fw-brand'><span>FW-LAB</span><button class='fw-toggle' id='fwCollapseBtn'>≡</button></div>
    <div class='fw-build' style='padding:0 .45rem .4rem'>build {BUILD_STAMP}</div>
    <nav class='fw-nav'>
      <a href='/'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 10.5 12 3l9 7.5'/><path d='M5 9.5V21h14V9.5'/></svg></span><span class='fw-label'>Dashboard</span></a>
      <a href='/events'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><rect x='4' y='4' width='16' height='16' rx='2'/><path d='M8 9h8M8 13h8M8 17h5'/></svg></span><span class='fw-label'>Events</span></a>
      <a href='/radio'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 12h3m12 0h3'/><circle cx='12' cy='12' r='2.5'/><path d='M6.5 8.5a8 8 0 0 1 0 7M17.5 8.5a8 8 0 0 1 0 7'/></svg></span><span class='fw-label'>Radio</span></a>
      <a href='/trends'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M4 19h16'/><path d='m6 15 4-4 3 2 5-6'/><path d='m18 7 0 3h-3'/></svg></span><span class='fw-label'>Trends</span></a>
      <a href='/admin'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='3'/><path d='M19.4 15a1 1 0 0 0 .2 1.1l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9V20a2 2 0 0 1-4 0v-.2a1 1 0 0 0-.6-.9 1 1 0 0 0-1.1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6H4a2 2 0 0 1 0-4h.2a1 1 0 0 0 .9-.6 1 1 0 0 0-.2-1.1l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1 1 0 0 0 1.1.2h0a1 1 0 0 0 .6-.9V4a2 2 0 0 1 4 0v.2a1 1 0 0 0 .6.9h0a1 1 0 0 0 1.1-.2l.1-.1a2 2 0 0 1 2.8 2.8l-.1.1a1 1 0 0 0-.2 1.1v0a1 1 0 0 0 .9.6H20a2 2 0 0 1 0 4h-.2a1 1 0 0 0-.9.6z'/></svg></span><span class='fw-label'>Admin</span></a>
      <a href='/forensics'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='11' cy='11' r='6.5'/><path d='M20 20l-4.2-4.2'/><path d='M11 8.5v5M8.5 11h5'/></svg></span><span class='fw-label'>Forensics</span></a>
      <a href='/about'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='9'/><path d='M12 11v5'/><circle cx='12' cy='8' r='1'/></svg></span><span class='fw-label'>About</span></a>
    </nav>
  </aside>
</div>
<script>
(function(){{
  var sb=document.getElementById('fwSidebar');
  var collapseBtn=document.getElementById('fwCollapseBtn');
  var mBtn=document.getElementById('fwMobileToggle');
  var path=window.location.pathname||'/';
  document.querySelectorAll('.fw-nav a').forEach(function(a){{
    if(a.getAttribute('href')===path) a.classList.add('active');
    a.addEventListener('click', function(){{ if(window.innerWidth<=860) sb.classList.remove('open'); }});
  }});
  function applyMain(){{
    var page=document.querySelector('.page')||document.querySelector('.wrap');
    if(!page) return;
    page.classList.add('fw-main');
    page.style.paddingTop = (window.innerWidth<=860) ? '.45rem' : '1rem';
    if(sb.classList.contains('collapsed')) page.classList.add('nav-collapsed'); else page.classList.remove('nav-collapsed');
  }}
  var collapsed=localStorage.getItem('fw_sidebar_collapsed')==='1';
  if(collapsed) sb.classList.add('collapsed');
  applyMain();
  if(collapseBtn) collapseBtn.onclick=function(){{ sb.classList.toggle('collapsed'); localStorage.setItem('fw_sidebar_collapsed', sb.classList.contains('collapsed')?'1':'0'); applyMain(); }};
  if(mBtn) mBtn.onclick=function(){{ sb.classList.toggle('open'); }};
}})();
</script>
"""

HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Dashboard</title>
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
th,td{border-bottom:1px solid #243243;padding:.4rem;text-align:left;vertical-align:top}
thead th{position:sticky;top:0;background:#17212b;z-index:5}
tr.ok{background:rgba(75,160,98,.10)}
tr.warn{background:rgba(220,170,80,.12)}
tr.error{background:rgba(200,80,80,.14)}
tr.inline-detail td{background:#0f141a}
#rows tr{cursor:pointer}
#rows tr:hover td{background:rgba(127,200,255,.08)}
#rows tr:active td{background:rgba(127,200,255,.16)}
tr.selected td{box-shadow: inset 0 0 0 2px #4fa8ff;background:rgba(79,168,255,.18) !important}
pre{white-space:pre-wrap;word-break:break-word;background:#0f141a;padding:.6rem;border-radius:6px;border:1px solid #2a3948;max-height:240px;overflow:auto}
.detail-bits{display:flex;flex-wrap:wrap;gap:2px;background:#0f141a;border:1px solid #2a3948;border-radius:6px;padding:.35rem;margin-top:.4rem}
.detail-bits .b{width:10px;height:14px;border-radius:2px;display:inline-block}
.detail-bits .one{background:#68b8ff}
.detail-bits .zero{background:#2b3642}
.small{font-size:.9em}
</style>
<script src='https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'></script>
</head>
<body>
<div class='page'>
  <h2 id='pageTitle' style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 10.5 12 3l9 7.5'/><path d='M5 9.5V21h14V9.5'/></svg></span><span>Dashboard</span></h2>
  __NAV__

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
      <div class='muted small'>Rx charts source: <span id='rx-source'>fallback</span></div>
      <div class='muted small'>Rx packets per 2 min (last 30 min)</div>
      <div id='rx-chart' style='height:150px'></div>
      <div class='muted small' style='margin-top:.55rem'>Rx packets per 30 min (last 24 h)</div>
      <div id='rx-chart-24h' style='height:150px'></div>
      <div class='muted small'>Note: 30-min bins are phase-shifted by +15 min (…:15 to …:45 boundaries).</div>
    </div>

    <div class='card'>
      Host metrics: <span id='hm-status' class='muted'>n/a</span> · CPU <span id='hm-cpu'>-</span>% · RAM <span id='hm-mem'>-</span>% · Disk <span id='hm-disk'>-</span>% · Temp <span id='hm-temp'>-</span>°C · Load/core <span id='hm-load'>-</span> · Breaches <span id='hm-breach'>0</span>
    </div>


    <div class='card'>
      Storage: <span id='st-mode' class='muted'>n/a</span> · Used <span id='st-used'>-</span>% · Free <span id='st-free'>-</span> GB · Retention <span id='st-days'>-</span> days
    </div>

    <div id='detailTop' class='card' style='display:none'>
      <div id='detailTopHeader' class='muted' style='cursor:pointer;display:flex;align-items:center;gap:.4rem;justify-content:space-between'>
        <span>Drill-down (click this header to close)</span>
        <span>
          <button id='detailTail'>Tail: ON</button>
          <button id='detailPrev'>◀ Prev</button>
          <button id='detailNext'>Next ▶</button>
        </span>
      </div>
      <pre id='detailText'>No event selected.</pre>
      <div class='muted small' style='margin-top:.35rem'>Frame bits (graphical)</div>
      <div id='detailBits' class='detail-bits'></div>
    </div>
  </div>

  <div id='data-section'>
  <div id='table-controls-card' class='card'>
    <span class='muted'>Table controls:</span>
    <button id='filtersToggle' style='margin-left:.4rem'>Hide filters</button><br>
    <div id='filtersInner' style='margin-top:.35rem'>
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
  </div>
  <div class='table-wrap'>
    <table><thead><tr><th>Time</th><th>Status</th><th>Score</th><th>Ones Ratio</th><th>SNR (dB)</th><th>Conf</th><th>Errs</th><th>Sensor</th><th>Format</th><th>Data</th><th>Summary</th></tr></thead><tbody id='rows'></tbody></table>
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
  var filtersToggle=document.getElementById('filtersToggle');
  var filtersInner=document.getElementById('filtersInner');
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
  var detailBits=document.getElementById('detailBits');
  var detailTop=document.getElementById('detailTop');
  var detailTopHeader=document.getElementById('detailTopHeader');
  var detailPrev=document.getElementById('detailPrev');
  var detailNext=document.getElementById('detailNext');
  var detailTail=document.getElementById('detailTail');
  if(detailTop && !isEventsPage){ detailTop.style.display='none'; }
  function eventKey(evt){ return String(g(evt,'ts','')) + '|' + String(g(g(evt,'decode',{}),'sensor_id','')) + '|' + String(g(g(evt,'decode',{}),'data_val','')); }

  if(detailTopHeader){
    detailTopHeader.addEventListener('click', function(ev){
      if(ev && ev.target && (ev.target.id==='detailPrev' || ev.target.id==='detailNext')) return;
      setTailMode(false);
      selectedDetailKey='';
      if(detailTop){ detailTop.style.display='none'; }
      if(detailBits){ detailBits.innerHTML=''; }
      clearInlineDetail();
      render();
    });
  }

  function filteredEventsDesc(){
    var out=[];
    for(var i=events.length-1;i>=0;i--){ var ev=events[i]; if(passFilter(ev)) out.push(ev); }
    return out;
  }

  function setTailMode(on){
    tailMode = !!on;
    if(detailTail){ detailTail.textContent = tailMode ? 'Tail: ON' : 'Tail: OFF'; }
  }

  function refreshTailDetail(){
    if(!tailMode) return;
    if(!events.length) return;
    var latest = events[events.length-1];
    selectedDetailKey = eventKey(latest);
    if(detailTop){ detailTop.style.display='block'; detailText.textContent=detailPayload(latest); }
    renderDetailBits(latest);
  }

  function navDetail(step){
    setTailMode(false);
    var list=filteredEventsDesc();
    if(!list.length) return;
    var idx=0;
    if(selectedDetailKey){
      for(var i=0;i<list.length;i++){ if(eventKey(list[i])===selectedDetailKey){ idx=i; break; } }
    }
    var ni=idx+step;
    if(ni<0) ni=0;
    if(ni>=list.length) ni=list.length-1;
    var ev=list[ni];
    selectedDetailKey=eventKey(ev);
    if(detailTop){ detailTop.style.display='block'; detailText.textContent=detailPayload(ev); }
    renderDetailBits(ev);
    render();
  }
  if(detailPrev){ detailPrev.addEventListener('click', function(e){ e.stopPropagation(); navDetail(1); }); }
  if(detailNext){ detailNext.addEventListener('click', function(e){ e.stopPropagation(); navDetail(-1); }); }
  if(detailTail){ detailTail.addEventListener('click', function(e){ e.stopPropagation(); setTailMode(!tailMode); if(tailMode){ refreshTailDetail(); render(); } }); }
  if(isEventsPage && window.innerWidth<=860 && filtersInner){ filtersInner.style.display='none'; if(filtersToggle) filtersToggle.textContent='Show filters'; }
  if(isEventsPage){
    var t=document.getElementById('pageTitle');
    if(t){
      t.innerHTML = "<span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><rect x='4' y='4' width='16' height='16' rx='2'/><path d='M8 9h8M8 13h8M8 17h5'/></svg></span><span>Events</span>";
    }
  }
  if(filtersToggle){ filtersToggle.addEventListener('click', function(){
    if(!filtersInner) return;
    var hidden = (filtersInner.style.display==='none');
    filtersInner.style.display = hidden ? '' : 'none';
    filtersToggle.textContent = hidden ? 'Hide filters' : 'Show filters';
  }); }
  var rxChartEl=document.getElementById('rx-chart');
  var rxChart=(window.echarts && rxChartEl) ? echarts.init(rxChartEl) : null;
  var rxSourceEl=document.getElementById('rx-source');
  var rxChart24El=document.getElementById('rx-chart-24h');
  var rxChart24=(window.echarts && rxChart24El) ? echarts.init(rxChart24El) : null;
  var rfFreqNow=document.getElementById('rf-freq-now'), rfGainNow=document.getElementById('rf-gain-now'), rfSqNow=document.getElementById('rf-sq-now');
  var rfFreqSet=document.getElementById('rf-freq-set'), rfGainSet=document.getElementById('rf-gain-set'), rfSqSet=document.getElementById('rf-sq-set');
  var rfApply=document.getElementById('rf-apply'), rfMsg=document.getElementById('rf-msg');
  var rxStart=document.getElementById('rx-start'), rxStop=document.getElementById('rx-stop'), rxRestart=document.getElementById('rx-restart');
  var events=[];
  var rxAgg=null;
  var inlineRow=null;
  var selectedDetailKey='';
  var tailMode=true;

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

    if(rxAgg && rxAgg.rx_2m_30m && rxAgg.rx_2m_30m.counts && rxAgg.rx_2m_30m.labels){
      counts = rxAgg.rx_2m_30m.counts.slice(0, bins);
      labels = rxAgg.rx_2m_30m.labels.slice(0, bins);
      if(rxSourceEl){ rxSourceEl.textContent='sidecar'; rxSourceEl.className='good'; }
    } else {
      if(rxSourceEl){ rxSourceEl.textContent='fallback'; rxSourceEl.className='warn'; }
      for(var b=0;b<bins;b++){
        var ageStartMin = Math.round(((bins-b)*binMs)/60000);
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
    }

    rxChart.setOption({
      animation:false,
      grid:{left:36,right:12,top:18,bottom:24},
      xAxis:{type:'category',data:labels,axisLabel:{color:'#b6c2cf',fontSize:10},axisLine:{lineStyle:{color:'#2a3948'}}},
      yAxis:{type:'value',minInterval:1,axisLabel:{color:'#b6c2cf',fontSize:10},splitLine:{lineStyle:{color:'#2a3948'}}},
      tooltip:{trigger:'axis'},
      series:[{type:'bar',data:counts,itemStyle:{color:'#7fc8ff'},barMaxWidth:14}]
    }, true);

    if(rxChart24){
      var bins24=48; // 48 x 30min = 24h
      var counts24=new Array(bins24).fill(0);
      var labels24=new Array(bins24);

      if(rxAgg && rxAgg.rx_30m_24h && rxAgg.rx_30m_24h.counts && rxAgg.rx_30m_24h.labels){
        counts24 = rxAgg.rx_30m_24h.counts.slice(0, bins24);
        labels24 = rxAgg.rx_30m_24h.labels.slice(0, bins24);
      } else {
        var windowMs24=24*60*60*1000;
        var binMs24=30*60*1000;
        var phaseMs=15*60*1000; // shift bins to :15/:45 boundaries
        for(var b2=0;b2<bins24;b2++){
          var ageH=((bins24-b2)*binMs24)/3600000;
          labels24[b2]='-'+Math.round(ageH)+'h';
          if(b2===bins24-1) labels24[b2]='now';
        }
        for(var ii=0;ii<events.length;ii++){
          var t2=Date.parse(g(events[ii],'ts',''));
          if(!isFinite(t2)) continue;
          var age2=now-t2;
          if(age2<0 || age2>windowMs24) continue;
          var idx2=bins24-1-Math.floor((age2+phaseMs)/binMs24);
          if(idx2>=0 && idx2<bins24) counts24[idx2]++;
        }
      }
      rxChart24.setOption({
        animation:false,
        grid:{left:36,right:12,top:18,bottom:24},
        xAxis:{type:'category',data:labels24,axisLabel:{color:'#b6c2cf',fontSize:10,interval:3},axisLine:{lineStyle:{color:'#2a3948'}}},
        yAxis:{type:'value',minInterval:1,axisLabel:{color:'#b6c2cf',fontSize:10},splitLine:{lineStyle:{color:'#2a3948'}}},
        tooltip:{trigger:'axis'},
        series:[{type:'bar',data:counts24,itemStyle:{color:'#5fa8ff'},barMaxWidth:10}]
      }, true);
    }
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
      ts:g(evt,'ts',''),
      status:g(evt,'status',''),
      summary:g(evt,'summary',''),
      frame:{
        payload_hex:g(fr,'payload_hex',''),
        bits_preview:String(g(fr,'payload_bits','')).slice(0,128),
        start_bit:g(fr,'start_bit',null),
        stop_bit:g(fr,'stop_bit',null)
      },
      errors:g(evt,'errors',[]),
      decode:g(evt,'decode',{}),
      quality:g(evt,'quality',{}),
      rx:g(evt,'rx',{}),
      display:g(evt,'display',''),
      schema:g(evt,'schema','')
    }, null, 2);
  }

  function renderDetailBits(evt){
    if(!detailBits) return;
    var fr=g(evt,'frame',{}), bits=String(g(fr,'payload_bits',''));
    if(!bits){ detailBits.innerHTML=''; return; }
    var h='';
    for(var i=0;i<bits.length;i++){
      var b=bits[i]==='1'?'one':'zero';
      h += '<span class="b '+b+'" title="bit '+i+': '+bits[i]+'"></span>';
    }
    detailBits.innerHTML=h;
  }

  function clearInlineDetail(){
    if(inlineRow && inlineRow.parentNode){ inlineRow.parentNode.removeChild(inlineRow); }
    inlineRow=null;
  }

  function showDetail(tr, evt){
    setTailMode(false);
    var key = eventKey(evt);
    if(selectedDetailKey === key){
      selectedDetailKey = '';
      clearInlineDetail();
      if(detailTop){ detailTop.style.display='none'; }
      if(detailBits){ detailBits.innerHTML=''; }
      return;
    }
    selectedDetailKey = key;

    var text=detailPayload(evt);
    if(detailMode.value==='top'){
      clearInlineDetail();
      if(detailTop){ detailTop.style.display='block'; detailText.textContent=text; renderDetailBits(evt); }
      render();
      return;
    }
    if(detailTop){ detailTop.style.display='none'; }
    clearInlineDetail();
    inlineRow=document.createElement('tr'); inlineRow.className='inline-detail';
    var td=document.createElement('td'); td.colSpan=11;
    var pre=document.createElement('pre'); pre.textContent=text;
    td.appendChild(pre); inlineRow.appendChild(td);
    tr.parentNode.insertBefore(inlineRow, tr.nextSibling);
  }

  function renderRfNow(){
    if(!rfFreqNow || !rfGainNow || !rfSqNow) return;
    if(!events.length) return;
    var ev = events[events.length-1] || {};
    var rx = g(ev,'rx',{});
    rfFreqNow.textContent = (rx.center_freq_hz!=null?rx.center_freq_hz:'-');
    rfGainNow.textContent = (rx.rf_gain_db!=null?rx.rf_gain_db:'-');
    rfSqNow.textContent = (rx.rf_squelch_db!=null?rx.rf_squelch_db:'-');
  }

  function loadRfConfig(){
    if(!rfFreqSet || !rfGainSet || !rfSqSet) return;
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
      if(selectedDetailKey && eventKey(ev)===selectedDetailKey){ tr.classList.add('selected'); }
      var q=g(g(ev,'quality',{}),'score',null); q=(typeof q==='number')?q.toFixed(3):'';
      var qy=g(ev,'quality',{});
      var c=g(qy,'confidence','');
      var or=g(qy,'ones_ratio',null); or=(typeof or==='number')?or.toFixed(3):'';
      var snr=g(qy,'snr_db_proxy',null); snr=(typeof snr==='number')?snr.toFixed(2):'';
      var errs=g(ev,'errors',[]); var errN=(errs&&errs.length)?errs.length:0;
      var errCodes=(errs||[]).map(function(e){return g(e,'code','');});
      function hasErr(prefix){ for(var ei=0;ei<errCodes.length;ei++){ if(String(errCodes[ei]).indexOf(prefix)===0) return true; } return false; }
      var de=g(ev,'decode',{});
      var sid=g(de,'sensor_id','');
      var sidLink = (sid!=='' && sid!==null && sid!==undefined) ? ('<a style="color:#7fc8ff" href="/trends?sensor_id='+encodeURIComponent(String(sid))+'&window=24h">'+sid+'</a>') : '';

      var orHtml = hasErr('signal.bit_balance_extreme') ? ('<span class="bad">'+or+'</span>') : or;
      var snrHtml = hasErr('signal.low_snr_proxy') ? ('<span class="bad">'+snr+'</span>') : snr;
      var fmtHtml = hasErr('decode.invalid_format_id') ? ('<span class="bad">'+g(de,'format_id','')+'</span>') : g(de,'format_id','');
      var sidHtml = hasErr('decode.zero_sensor_id') ? ('<span class="bad">'+sidLink+'</span>') : sidLink;
      var summaryHtml = (errN>0) ? ('<span class="warn">'+g(ev,'summary','')+'</span>') : g(ev,'summary','');

      tr.innerHTML='<td>'+fmtTs(g(ev,'ts',''))+'</td><td>'+g(ev,'status','')+'</td><td>'+q+'</td><td>'+orHtml+'</td><td>'+snrHtml+'</td><td>'+c+'</td><td>'+errN+'</td><td>'+sidHtml+'</td><td>'+fmtHtml+'</td><td>'+g(de,'data_val','')+'</td><td>'+summaryHtml+'</td>';
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
  if(rfApply){
    rfApply.addEventListener('click', function(){
      var body={
        center_freq_hz: rfFreqSet.value.trim()==='' ? null : Number(rfFreqSet.value),
        rf_gain_db: rfGainSet.value.trim()==='' ? null : Number(rfGainSet.value),
        rf_squelch_db: rfSqSet.value.trim()==='' ? null : Number(rfSqSet.value)
      };
      fetch('/api/admin/rf_control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
        .then(function(r){return r.json();})
        .then(function(d){ if(rfMsg) rfMsg.textContent = d.ok ? ' saved (restart receiver to apply)' : ' failed'; })
        ['catch'](function(){ if(rfMsg) rfMsg.textContent=' failed'; });
    });
  }

  function receiverAction(action){
    fetch('/api/admin/receiver_action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:action})})
      .then(function(r){return r.json();})
      .then(function(d){ if(rfMsg) rfMsg.textContent = d.ok ? (' receiver '+action+' ok') : (' receiver '+action+' failed'); })
      ['catch'](function(){ if(rfMsg) rfMsg.textContent=' receiver '+action+' failed'; });
  }
  if(rxStart) rxStart.addEventListener('click', function(){ receiverAction('start'); });
  if(rxStop) rxStop.addEventListener('click', function(){ receiverAction('stop'); });
  if(rxRestart) rxRestart.addEventListener('click', function(){ receiverAction('restart'); });

  if(isEventsPage){ setTailMode(true); }
  fetch('/api/events?limit=400').then(function(r){return r.json();}).then(function(d){events=d.events||[]; source.textContent=g(d,'source','n/a'); if(isEventsPage){ refreshTailDetail(); } render();});
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
  function pollRxAgg(){
    fetch('/api/rx_agg').then(function(r){ if(!r.ok) return null; return r.json(); }).then(function(d){ if(d){ rxAgg=d; drawRxBars(); } else { rxAgg=null; drawRxBars(); } })['catch'](function(){ rxAgg=null; drawRxBars(); });
  }
  pollHost(); setInterval(pollHost,3000);
  pollReceiver(); setInterval(pollReceiver,5000);
  pollStorage(); setInterval(pollStorage,10000);
  pollRxAgg(); setInterval(pollRxAgg,10000);

  var es=new EventSource('/api/live');
  es.onmessage=function(m){
    try{
      events.push(JSON.parse(m.data));
      if(events.length>4000) events=events.slice(-4000);
      fetch('/api/events?limit=1').then(function(r){return r.json();}).then(function(d){ source.textContent=g(d,'source','n/a'); })['catch'](function(){});
      if(isEventsPage){ refreshTailDetail(); }
      render();
      status.textContent='live';
    }catch(e){}
  };
  es.onerror=function(){ status.textContent='reconnecting'; };
  window.addEventListener('resize', function(){ if(rxChart) rxChart.resize(); if(rxChart24) rxChart24.resize(); });
})();
</script></body></html>"""

ADMIN_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Admin</title>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,button,select{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}a{color:#7fc8ff}.row{margin:.35rem 0}.grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:.6rem}.good{color:#6dd17c}.warn{color:#f2c14e}.bad{color:#f36f6f}pre{white-space:pre-wrap;max-height:220px;overflow:auto;background:#0f141a;border:1px solid #2a3948;padding:.55rem;border-radius:6px}@media(max-width:860px){.grid{grid-template-columns:1fr}input,button,select{min-height:40px;font-size:16px}}</style></head>
<body><div class='page'>
<h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='3'/><path d='M19.4 15a1 1 0 0 0 .2 1.1l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9V20a2 2 0 0 1-4 0v-.2a1 1 0 0 0-.6-.9 1 1 0 0 0-1.1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6H4a2 2 0 0 1 0-4h.2a1 1 0 0 0 .9-.6 1 1 0 0 0-.2-1.1l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1 1 0 0 0 1.1.2h0a1 1 0 0 0 .6-.9V4a2 2 0 0 1 4 0v.2a1 1 0 0 0 .6.9h0a1 1 0 0 0 1.1-.2l.1-.1a2 2 0 0 1 2.8 2.8l-.1.1a1 1 0 0 0-.2 1.1v0a1 1 0 0 0 .9.6H20a2 2 0 0 1 0 4h-.2a1 1 0 0 0-.9.6z'/></svg></span><span>Admin</span></h2>
__NAV__
<div class='card'>
  <div class='grid'>
    <div>Receiver: <strong id='rxState'>unknown</strong></div>
    <div>Storage mode: <strong id='stMode'>n/a</strong></div>
    <div>Disk used: <strong id='stUsed'>-</strong>%</div>
  </div>
  <div class='row' style='margin-top:.6rem'>
    <button id='rxStart'>Start receiver</button>
    <button id='rxStop'>Stop receiver</button>
    <button id='rxRestart'>Restart receiver</button>
  </div>
</div>

<div class='card'>
  <h3 style='margin:.1rem 0 .6rem'>Storage policy</h3>
  <div class='row'>Local retention days: <input id='localDays' type='number' step='0.1'></div>
  <div class='row'>Max local MB: <input id='maxMb' type='number' step='1'></div>
  <div class='row'>Warn disk %: <input id='warnPct' type='number' step='0.1'></div>
  <div class='row'>Critical disk %: <input id='critPct' type='number' step='0.1'></div>
  <div class='row'>Emergency disk %: <input id='emerPct' type='number' step='0.1'></div>
  <div class='row'>Critical retention days: <input id='critDays' type='number' step='0.1'></div>
  <div class='row'>Emergency retention hours: <input id='emerHours' type='number' step='1'></div>
  <button id='save'>Save policy</button> <span id='msg'></span>
</div>

<div class='card'>
  <h3 style='margin:.1rem 0 .6rem'>Recent admin audit</h3>
  <button id='copyDiag'>Copy diagnostics snapshot</button>
  <pre id='audit'>loading...</pre>
</div>
<script>
(function(){
  function g(o,k,d){ return (o && o[k]!==undefined && o[k]!==null) ? o[k] : d; }
  function setv(id,v){ document.getElementById(id).value = (v==null?'':v); }
  function num(id){ var x=parseFloat(document.getElementById(id).value); return isNaN(x)?null:x; }
  var lastPolicy=null, lastReceiver=null, lastStorage=null, lastAudit=[];

  function load(){
    fetch('/api/admin/storage_policy').then(function(r){return r.json();}).then(function(p){
      lastPolicy = p || {};
      var th = g(p,'thresholds',{}), cp = g(p,'criticalPolicy',{});
      setv('localDays', g(p,'localRetentionDays','')); setv('maxMb', g(p,'maxLocalMb',''));
      setv('warnPct', g(th,'warnDiskPercent','')); setv('critPct', g(th,'criticalDiskPercent','')); setv('emerPct', g(th,'emergencyDiskPercent',''));
      setv('critDays', g(cp,'criticalRetentionDays','')); setv('emerHours', g(cp,'emergencyRetentionHours',''));
    }).catch(function(){ document.getElementById('msg').textContent=' failed to load policy'; });
  }
  function pollStatus(){
    fetch('/api/receiver_status').then(function(r){return r.json();}).then(function(d){
      lastReceiver = d || {};
      var el=document.getElementById('rxState');
      var st=g(d,'state','unknown');
      el.textContent=st;
      el.className=(st==='online')?'good':((st==='stale')?'warn':'bad');
    }).catch(function(){});
    fetch('/api/storage_status').then(function(r){return r.json();}).then(function(d){
      lastStorage = d || {};
      document.getElementById('stMode').textContent=g(d,'mode','n/a');
      document.getElementById('stUsed').textContent=(g(d,'disk_used_percent',null)!=null?g(d,'disk_used_percent','-'):'-');
    }).catch(function(){});
  }
  function loadAudit(){
    fetch('/api/admin/audit_recent?limit=20').then(function(r){return r.json();}).then(function(d){
      var rows=g(d,'events',[])||[];
      lastAudit = rows;
      document.getElementById('audit').textContent = rows.map(function(e){
        return (g(e,'ts',''))+'  '+(g(e,'ok',false)?'OK ':'ERR')+'  '+(g(e,'action',''))+'  '+JSON.stringify(g(e,'details',{}));
      }).join('\\n') || 'no audit events yet';
    }).catch(function(){ document.getElementById('audit').textContent='failed to load audit'; });
  }
  function receiverAction(action){
    fetch('/api/admin/receiver_action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:action})})
      .then(function(r){return r.json();})
      .then(function(d){ document.getElementById('msg').textContent = d.ok ? (' receiver '+action+' ok') : (' receiver '+action+' failed'); loadAudit(); pollStatus(); });
  }
  document.getElementById('rxStart').addEventListener('click', function(){ receiverAction('start'); });
  document.getElementById('rxStop').addEventListener('click', function(){ receiverAction('stop'); });
  document.getElementById('rxRestart').addEventListener('click', function(){ receiverAction('restart'); });

  document.getElementById('save').addEventListener('click', function(){
    var body={
      localRetentionDays:num('localDays'),
      maxLocalMb:num('maxMb'),
      thresholds:{warnDiskPercent:num('warnPct'),criticalDiskPercent:num('critPct'),emergencyDiskPercent:num('emerPct')},
      criticalPolicy:{criticalRetentionDays:num('critDays'),emergencyRetentionHours:num('emerHours')}
    };
    fetch('/api/admin/storage_policy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      .then(function(r){return r.json();})
      .then(function(d){ document.getElementById('msg').textContent = d.ok ? ' saved' : ' failed'; load(); loadAudit(); pollStatus(); });
  });

  document.getElementById('copyDiag').addEventListener('click', function(){
    var snap = {
      ts: new Date().toISOString(),
      receiver: lastReceiver || {},
      storage: lastStorage || {},
      policy: lastPolicy || {},
      audit_recent: lastAudit || []
    };
    var txt = JSON.stringify(snap, null, 2);
    navigator.clipboard.writeText(txt).then(function(){
      document.getElementById('msg').textContent=' diagnostics copied';
    }).catch(function(){
      document.getElementById('msg').textContent=' copy failed';
    });
  });

  load();
  pollStatus(); setInterval(pollStatus,5000);
  loadAudit(); setInterval(loadAudit,12000);
})();
</script></div></body></html>"""

TRENDS_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Trends</title>
<script src='https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'></script>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,select,button{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}a{color:#7fc8ff}#chart{height:420px}.controls{display:flex;flex-wrap:wrap;gap:.35rem .5rem;align-items:center}@media(max-width:860px){.controls{display:grid;grid-template-columns:1fr 1fr;gap:.45rem}#chart{height:320px}input,select,button{min-height:40px;font-size:16px}}</style></head>
<body><div class='page'>
<h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M4 19h16'/><path d='m6 15 4-4 3 2 5-6'/><path d='m18 7 0 3h-3'/></svg></span><span>Trends</span></h2>
__NAV__<br><br>
<div class='card controls'>
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

RADIO_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Radio</title>
<style>
body{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#0f141a;color:#e6edf3;margin:0}
.wrap{max-width:1200px;margin:0 auto;padding:1rem}
.card{background:#17212b;border:1px solid #243243;border-radius:10px;padding:.8rem;margin:.6rem 0}
@media (max-width: 860px){#radioAudioCard{position:sticky;top:46px;z-index:105}}
.row{display:flex;gap:1rem;flex-wrap:wrap}
.kpi{min-width:180px}.muted{color:#9fb0c3}.good{color:#6dd17c}.warn{color:#f2c14e}.bad{color:#f36f6f}
pre{margin:0;white-space:pre-wrap;word-break:break-word;font-size:.86rem}
</style>
<script src='https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'></script></head><body><div class='wrap'>
  <h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 12h3m12 0h3'/><circle cx='12' cy='12' r='2.5'/><path d='M6.5 8.5a8 8 0 0 1 0 7M17.5 8.5a8 8 0 0 1 0 7'/></svg></span><span>Radio</span></h2>
  __NAV__
  <div id='radioAudioCard' class='card'><strong>Radio Live</strong> <span class='muted'>· Real-time RF/decode health</span> · <button id='freezeBtn'>Freeze</button> <span id='freezeState' class='muted'>live</span> · <button id='audioBtn'>Load Audio</button> <span id='audioState' class='muted'>off</span> · Codec: <select id='audioCodec'><option value='auto' selected>auto</option><option value='opus'>opus</option><option value='aac'>aac</option></select> · Gain <input id='audioGain' type='number' min='0.5' max='4.0' step='0.1' value='1.6' style='width:70px'><br><audio id='audioPlayer' controls playsinline preload='none' style='margin-top:.35rem;width:100%'></audio><div class='muted' style='margin-top:.25rem'>If blocked on iOS, tap play on the native control above. Test links: <a href='/api/audio_aac' target='_blank' style='color:#7fc8ff'>aac</a> · <a href='/api/audio_opus' target='_blank' style='color:#7fc8ff'>opus</a></div></div>
  <div class='card'>
    RF now: Freq <span id='rf-freq-now'>-</span> Hz · Gain <span id='rf-gain-now'>-</span> dB · Squelch <span id='rf-sq-now'>-</span> dB<br>
    RF control (pending/apply on receiver restart):
    Freq <input id='rf-freq-set' style='width:140px' placeholder='173900000'>
    Gain <input id='rf-gain-set' style='width:80px' placeholder='40'>
    Squelch <input id='rf-sq-set' style='width:80px' placeholder='-33'>
    <button id='rf-apply'>Save RF config</button>
    <button id='rx-start'>Start receiver</button>
    <button id='rx-stop'>Stop receiver</button>
    <button id='rx-restart'>Restart receiver</button>
    <span id='rf-msg' class='muted'></span>
  </div>
  <div class='row'>
    <div class='card kpi'>Receiver<br><strong id='rx'>unknown</strong></div>
    <div class='card kpi'>Events/min<br><strong id='rate'>0.0</strong></div>
    <div class='card kpi'>Ones ratio avg<br><strong id='ones'>n/a</strong></div>
    <div class='card kpi'>Top error<br><strong id='toperr'>none</strong></div>
  </div>
  <div class='card'><strong>Latest symbol waveform</strong> · Source: <select id='wavesrc'><option value='symbol' selected>symbol_samples</option><option value='bits'>payload_bits step</option></select><div id='symchart' style='height:220px'></div></div>
  <div class='card'><strong>Symbol waterfall (recent frames)</strong><div id='wfchart' style='height:520px'></div></div>
  <div class='card'><strong>Recent error codes</strong><pre id='errs'>none</pre></div>
  <div class='card'><div id='chart' style='height:220px'></div></div>
</div>
<script>
(function(){
  function g(o,k,d){return (o&&o[k]!==undefined&&o[k]!==null)?o[k]:d;}
  var events=[]; var max=1200;
  var rx=document.getElementById('rx'), rate=document.getElementById('rate'), ones=document.getElementById('ones'), toperr=document.getElementById('toperr'), errs=document.getElementById('errs');
  var wavesrc=document.getElementById('wavesrc');
  var freezeBtn=document.getElementById('freezeBtn'), freezeState=document.getElementById('freezeState');
  var audioBtn=document.getElementById('audioBtn'), audioState=document.getElementById('audioState');
  var audioCodec=document.getElementById('audioCodec');
  var audioGain=document.getElementById('audioGain');
  var audioPlayer=document.getElementById('audioPlayer');
  var rfFreqNow=document.getElementById('rf-freq-now'), rfGainNow=document.getElementById('rf-gain-now'), rfSqNow=document.getElementById('rf-sq-now');
  var rfFreqSet=document.getElementById('rf-freq-set'), rfGainSet=document.getElementById('rf-gain-set'), rfSqSet=document.getElementById('rf-sq-set');
  var rfApply=document.getElementById('rf-apply'), rfMsg=document.getElementById('rf-msg');
  var rxStart=document.getElementById('rx-start'), rxStop=document.getElementById('rx-stop'), rxRestart=document.getElementById('rx-restart');
  var paused=false;
  var audioOn=false, audioEl=null;
  var chart=(window.echarts)?echarts.init(document.getElementById('chart')):null;
  var symchart=(window.echarts)?echarts.init(document.getElementById('symchart')):null;
  var wfchart=(window.echarts)?echarts.init(document.getElementById('wfchart')):null;

  function renderRfNow(){
    if(!events.length || !rfFreqNow) return;
    var ev=events[events.length-1]||{}, rxm=g(ev,'rx',{});
    rfFreqNow.textContent=(rxm.center_freq_hz!=null?rxm.center_freq_hz:'-');
    rfGainNow.textContent=(rxm.rf_gain_db!=null?rxm.rf_gain_db:'-');
    rfSqNow.textContent=(rxm.rf_squelch_db!=null?rxm.rf_squelch_db:'-');
  }

  function loadRfConfig(){
    if(!rfFreqSet) return;
    fetch('/api/admin/rf_control').then(function(r){return r.json();}).then(function(c){
      rfFreqSet.value=(c.center_freq_hz!=null?c.center_freq_hz:'');
      rfGainSet.value=(c.rf_gain_db!=null?c.rf_gain_db:'');
      rfSqSet.value=(c.rf_squelch_db!=null?c.rf_squelch_db:'');
    })['catch'](function(){});
  }

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
    errs.textContent=Object.keys(ec).sort(function(a,b){return ec[b]-ec[a];}).slice(0,10).map(function(k){return k+': '+ec[k];}).join('\\n') || 'none';

    renderRfNow();

    if(chart){
      var tail=events.slice(-200), xs=[], ys=[];
      tail.forEach(function(e){ var t=Date.parse(g(e,'ts','')); var q=g(e,'quality',{}), or=g(q,'ones_ratio',null); if(isFinite(t) && typeof or==='number'){ xs.push(new Date(t).toLocaleTimeString()); ys.push(or);} });
      chart.setOption({animation:false,grid:{left:40,right:12,top:20,bottom:28},xAxis:{type:'category',data:xs},yAxis:{type:'value',min:0,max:1},tooltip:{trigger:'axis'},series:[{type:'line',data:ys,symbol:'none'}]});
    }

    if(symchart){
      var sym=[];
      if((wavesrc && wavesrc.value)==='bits'){
        for(var i=events.length-1;i>=0;i--){
          var frb=g(events[i],'frame',{}), pb=String(g(frb,'payload_bits',''));
          if(pb){
            for(var b=0;b<pb.length;b++) sym.push(pb[b]==='1'?1:-1);
            break;
          }
        }
      } else {
        for(var i=events.length-1;i>=0;i--){
          var fr=g(events[i],'frame',{}), s=g(fr,'symbol_samples',null);
          if(s && s.length){ sym=s; break; }
        }
      }
      var sx=[], sy=[];
      for(var j=0;j<sym.length;j++){ sx.push(String(j)); sy.push(Number(sym[j])); }
      symchart.setOption({
        animation:false,
        grid:{left:40,right:12,top:20,bottom:28},
        xAxis:{type:'category',data:sx},
        yAxis:{type:'value',min:-2,max:2,splitNumber:2,
          splitArea:{show:true,areaStyle:{color:['rgba(44,123,182,0.14)','rgba(215,25,28,0.12)']}},
          splitLine:{lineStyle:{color:'#2a3948'}}
        },
        tooltip:{trigger:'axis'},
        series:[{type:'line',data:sy,symbol:'none',step:'middle',lineStyle:{color:'#8fd1ff'}}]
      });
    }

    if(wfchart){
      var rows=[];
      for(var i=events.length-1;i>=0 && rows.length<40;i--){
        var fr=g(events[i],'frame',{}), s=g(fr,'symbol_samples',null);
        if(s && s.length) rows.push(s.map(function(v){return Number(v);}));
      }
      rows.reverse();
      var maxLen=0;
      for(var r=0;r<rows.length;r++) if(rows[r].length>maxLen) maxLen=rows[r].length;
      var data=[], xlabels=[], ylabels=[];
      for(var x=0;x<maxLen;x++) xlabels.push(String(x));
      for(var y=0;y<rows.length;y++){
        ylabels.push(String(y-rows.length+1));
        for(var x=0;x<rows[y].length;x++) data.push([x,y,rows[y][x]]);
      }
      wfchart.setOption({
        animation:false,
        grid:{left:46,right:18,top:20,bottom:28},
        xAxis:{type:'category',data:xlabels,name:'symbol'},
        yAxis:{type:'category',data:ylabels,name:'frames'},
        visualMap:{min:-1,max:1,orient:'horizontal',left:'center',bottom:0,inRange:{color:['#2c7bb6','#7fb8de','rgba(76,175,80,0.18)','#f4a06b','#d7191c']}},
        tooltip:{position:'top'},
        series:[{type:'heatmap',data:data,progressive:0,emphasis:{itemStyle:{borderColor:'#fff',borderWidth:1}}}]
      });
    }
  }

  function stopAudio(){
    audioOn=false;
    if(audioEl){ try{ audioEl.pause(); audioEl.src=''; }catch(e){} }
    if(audioState) audioState.textContent='off';
    if(audioBtn) audioBtn.textContent='Load Audio';
  }

  function startAudio(){
    try{
      if(!audioEl){
        audioEl = audioPlayer || new Audio();
        audioEl.autoplay = false;
        audioEl.preload = 'none';
        audioEl.controls = true;
        audioEl.onplaying = function(){ audioOn=true; if(audioState) audioState.textContent='on'; if(audioBtn) audioBtn.textContent='Unload Audio'; };
        audioEl.onpause = function(){ if(!audioOn) return; audioOn=false; if(audioState) audioState.textContent='paused'; if(audioBtn) audioBtn.textContent='Load Audio'; };
        audioEl.onerror = function(){ audioOn=false; if(audioState) audioState.textContent='stream error'; if(audioBtn) audioBtn.textContent='Load Audio'; };
        audioEl.onstalled = function(){ if(audioState) audioState.textContent='buffering'; };
      }

      var codec = (audioCodec && audioCodec.value) ? audioCodec.value : 'auto';
      var gain = (audioGain && audioGain.value) ? Number(audioGain.value) : 1.6;
      if(!isFinite(gain) || gain <= 0) gain = 1.6;
      var primary = (codec==='aac') ? '/api/audio_aac' : '/api/audio_opus';
      if(codec==='auto') primary = '/api/audio_aac';
      var sep = primary.indexOf('?')>=0 ? '&' : '?';
      audioEl.src = primary + sep + 'gain=' + encodeURIComponent(String(gain));
      audioEl.load();
      if(audioState) audioState.textContent='ready (press play on control)';
      if(audioBtn) audioBtn.textContent='Unload Audio';
    }catch(e){ if(audioState) audioState.textContent='error'; if(audioBtn) audioBtn.textContent='Load Audio'; }
  }

  if(audioBtn){ audioBtn.addEventListener('click', function(){ if(audioEl && audioEl.src){ stopAudio(); } else { startAudio(); } }); }
  if(audioCodec){ audioCodec.addEventListener('change', function(){ if(audioEl && audioEl.src){ startAudio(); } }); }
  if(audioGain){ audioGain.addEventListener('change', function(){ if(audioEl && audioEl.src){ startAudio(); } }); }

  if(rfApply){
    rfApply.addEventListener('click', function(){
      var body={
        center_freq_hz: rfFreqSet.value.trim()==='' ? null : Number(rfFreqSet.value),
        rf_gain_db: rfGainSet.value.trim()==='' ? null : Number(rfGainSet.value),
        rf_squelch_db: rfSqSet.value.trim()==='' ? null : Number(rfSqSet.value)
      };
      fetch('/api/admin/rf_control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
        .then(function(r){return r.json();})
        .then(function(d){ if(rfMsg) rfMsg.textContent = d.ok ? ' saved (restart receiver to apply)' : ' failed'; })
        ['catch'](function(){ if(rfMsg) rfMsg.textContent=' failed'; });
    });
  }

  function receiverAction(action){
    fetch('/api/admin/receiver_action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:action})})
      .then(function(r){return r.json();})
      .then(function(d){ if(rfMsg) rfMsg.textContent = d.ok ? (' receiver '+action+' ok') : (' receiver '+action+' failed'); })
      ['catch'](function(){ if(rfMsg) rfMsg.textContent=' receiver '+action+' failed'; });
  }
  if(rxStart) rxStart.addEventListener('click', function(){ receiverAction('start'); });
  if(rxStop) rxStop.addEventListener('click', function(){ receiverAction('stop'); });
  if(rxRestart) rxRestart.addEventListener('click', function(){ receiverAction('restart'); });

  loadRfConfig();
  fetch('/api/events?limit=800').then(function(r){return r.json();}).then(function(d){ events=d.events||[]; refresh(); })['catch'](function(){});
  var es=new EventSource('/api/live');
  es.onmessage=function(m){ try{ if(paused) return; events.push(JSON.parse(m.data)); if(events.length>max) events=events.slice(-max); refresh(); }catch(e){} };
  if(wavesrc){ wavesrc.addEventListener('input', refresh); }
  if(freezeBtn){ freezeBtn.addEventListener('click', function(){ paused=!paused; freezeBtn.textContent = paused ? 'Resume' : 'Freeze'; if(freezeState){ freezeState.textContent = paused ? 'frozen' : 'live'; } }); }
  window.addEventListener('beforeunload', function(){ stopAudio(); });
  window.addEventListener('resize', function(){ if(chart) chart.resize(); if(symchart) symchart.resize(); if(wfchart) wfchart.resize(); });
})();
</script></body></html>"""

FORENSICS_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Forensics</title>
<style>
body{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#0f141a;color:#e6edf3;margin:0}
.wrap{max-width:1280px;margin:0 auto;padding:1rem}
.card{background:#17212b;border:1px solid #243243;border-radius:10px;padding:.8rem;margin:.6rem 0}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:.6rem}
pre{white-space:pre-wrap;word-break:break-word;background:#0f141a;border:1px solid #2a3948;padding:.6rem;border-radius:8px;max-height:52vh;overflow:auto}
.muted{color:#9fb0c3}a{color:#7fc8ff}
@media(max-width:980px){.grid{grid-template-columns:1fr}}
</style></head><body><div class='wrap'>
<h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='11' cy='11' r='6.5'/><path d='M20 20l-4.2-4.2'/><path d='M11 8.5v5M8.5 11h5'/></svg></span><span>Forensics</span></h2>
__NAV__
<div class='card'>
  <strong>Purpose</strong><br>
  Non-daily deep diagnostics for SDR modulation/decode verification and SME review.
  <ul>
    <li>Flowgraph block inventory + connectivity extracted from <code>src/ALERT1v3.grc</code></li>
    <li>Decoder/error telemetry references for troubleshooting</li>
    <li>Hand-off material for external protocol/RF experts</li>
  </ul>
</div>
<div class='grid'>
  <div class='card'><strong>Flowgraph summary</strong><pre id='summary'>__FG_SUMMARY__</pre></div>
  <div class='card'><strong>Pipeline narrative (for SME review)</strong><pre id='narrative'>1) RTL-SDR source (complex IQ)
   - center frequency target and RF gain/squelch are the first-order sensitivity controls.

2) Channel conditioning
   - complex low-pass + decimation narrows to expected ALERT channel energy.

3) Frequency demodulation
   - quadrature demod converts FSK-like frequency swings into baseband amplitude swings.

4) Symbol conditioning + timing
   - AGC/LPF/symbol-sync stages shape and sample symbol decisions.
   - failure modes here often show as all-ones/all-zeros bias, framing mismatch, hunt timeouts.

5) Protocol framing / field extraction
   - decoder assembles 10-bit words and 4-word frames, validates framing/pattern constraints,
     then extracts sensor/address + data fields.

6) Quality and operations outputs
   - per-event quality/error taxonomy + logs/MQTT/web views for operator feedback and tuning.</pre></div>
</div>
<div class='card'><strong>Block inventory</strong><pre id='blocks'>__FG_BLOCKS__</pre></div>
<div class='card'><strong>Connections (src -> dst)</strong><pre id='conns'>__FG_CONNS__</pre></div>
<div class='card'><strong>Decode checklist</strong><pre id='check'>1) Confirm symbol timing and slicer behavior under real RF conditions.
2) Validate 10-bit framing assumptions (start/stop polarity, bit order).
3) Validate fixed pattern / CRC expectations against known-good captures.
4) Compare pre/post filter and demod taps for bias (e.g. all-ones drift).
5) Quantify quality metrics (ones_ratio, snr proxy, eye opening) over soak windows.</pre></div>
<div class='card'><button id='exportBundle'>Export SME bundle (.json)</button> <span id='exportMsg' class='muted'></span></div>
<script>
(function(){
  function g(o,k,d){ return (o&&o[k]!==undefined&&o[k]!==null)?o[k]:d; }
  var exportBtn=document.getElementById('exportBundle'), exportMsg=document.getElementById('exportMsg');

  if(exportBtn){
    exportBtn.addEventListener('click', function(){
      if(exportMsg) exportMsg.textContent=' building...';
      fetch('/api/forensics_bundle?limit=300').then(function(r){return r.json();}).then(function(d){
        var txt = JSON.stringify(d, null, 2);
        var blob = new Blob([txt], {type:'application/json;charset=utf-8'});
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'fwlab_forensics_bundle.json';
        a.click();
        URL.revokeObjectURL(url);
        if(exportMsg) exportMsg.textContent=' exported';
      }).catch(function(){ if(exportMsg) exportMsg.textContent=' export failed'; });
    });
  }
})();
</script></div></body></html>"""


def _forensics_bundle(store: 'EventStore', limit: int = 300):
    limit = max(10, min(int(limit), 2000))
    events = []
    if store:
        try:
            store.poll_new()
            events = list(store.events)[-limit:]
        except Exception:
            events = []
    cfg = {}
    for name, path in {
        'rf_control': 'config/rf_control.json',
        'storage_policy': 'config/storage_policy.json',
        'access_policy': 'config/access_policy.json',
    }.items():
        p = Path(path)
        if p.exists():
            try:
                cfg[name] = json.loads(p.read_text(encoding='utf-8', errors='replace'))
            except Exception:
                cfg[name] = {'error': 'parse_failed'}
        else:
            cfg[name] = {'error': 'missing'}

    return {
        'schema': 'fwlab.forensics.bundle.v1',
        'ts': datetime.utcnow().isoformat() + 'Z',
        'flowgraph': _flowgraph_doc(),
        'config': cfg,
        'events_limit': limit,
        'events': events,
    }


def _flowgraph_doc(grc_path='src/ALERT1v3.grc'):
    p = Path(grc_path)
    out = {
        'path': str(p),
        'exists': p.exists(),
        'generated_ts': datetime.utcnow().isoformat() + 'Z',
        'block_count': 0,
        'connection_count': 0,
        'blocks': [],
        'connections': [],
    }
    if not p.exists():
        return out
    try:
        d = yaml.safe_load(p.read_text(encoding='utf-8', errors='replace')) or {}
        blocks = d.get('blocks', []) or []
        conns = d.get('connections', []) or []
        out['blocks'] = [{'name': str(b.get('name','')), 'id': str(b.get('id',''))} for b in blocks if isinstance(b, dict)]
        parsed_conns = []
        for c in conns:
            if isinstance(c, list) and len(c) >= 4:
                parsed_conns.append({
                    'src_block': str(c[0]), 'src_port': str(c[1]),
                    'dst_block': str(c[2]), 'dst_port': str(c[3]),
                })
        out['connections'] = parsed_conns
        out['block_count'] = len(out['blocks'])
        out['connection_count'] = len(out['connections'])
    except Exception as e:
        out['error'] = str(e)
    return out


def _md_inline(s: str) -> str:
    x = html.escape(s)
    x = re.sub(r'`([^`]+)`', r'<code>\1</code>', x)
    x = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', x)
    x = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', x)
    x = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', x)
    return x


def markdown_to_html(md: str) -> str:
    lines = md.splitlines()
    out = []
    in_code = False
    in_ul = False
    para = []

    def flush_para():
        nonlocal para
        if para:
            out.append('<p>' + _md_inline(' '.join(para).strip()) + '</p>')
            para = []

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append('</ul>')
            in_ul = False

    for ln in lines:
        t = ln.rstrip('\n')
        if t.strip().startswith('```'):
            flush_para(); close_ul()
            if not in_code:
                out.append('<pre><code>'); in_code = True
            else:
                out.append('</code></pre>'); in_code = False
            continue

        if in_code:
            out.append(html.escape(t))
            continue

        s = t.strip()
        if not s:
            flush_para(); close_ul();
            continue

        m = re.match(r'^(#{1,6})\s+(.*)$', s)
        if m:
            flush_para(); close_ul()
            lvl = len(m.group(1))
            out.append(f'<h{lvl}>' + _md_inline(m.group(2)) + f'</h{lvl}>')
            continue

        if s.startswith('- ') or s.startswith('* '):
            flush_para()
            if not in_ul:
                out.append('<ul>'); in_ul = True
            out.append('<li>' + _md_inline(s[2:].strip()) + '</li>')
            continue

        para.append(s)

    flush_para(); close_ul()
    if in_code:
        out.append('</code></pre>')
    return '\n'.join(out)


def render_about_html():
    readme = Path('README.md')
    body = "README not found."
    if readme.exists():
        try:
            body = readme.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            body = f"Failed to read README.md: {e}"

    rendered = markdown_to_html(body)
    nav = NAV_HTML
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB About</title>
<style>
body{{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#0f141a;color:#e6edf3;margin:0}}
.wrap{{max-width:1200px;margin:0 auto;padding:1rem}}
.card{{background:#17212b;border:1px solid #243243;border-radius:10px;padding:.8rem;margin:.6rem 0}}
.md{{line-height:1.5}}
.md h1,.md h2,.md h3{{margin:.35rem 0 .5rem}}
.md p{{margin:.35rem 0}}
.md ul{{margin:.35rem 0 .6rem 1.2rem}}
.md pre{{white-space:pre-wrap;word-break:break-word;background:#101923;border:1px solid #2a3948;border-radius:8px;padding:.8rem;overflow:auto}}
.md code{{background:#111c27;padding:.08rem .3rem;border-radius:4px}}
a{{color:#7fc8ff}}
</style></head><body><div class='wrap'>
{nav}
<div class='card'><h2 style='margin:.2rem 0 0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='9'/><path d='M12 11v5'/><circle cx='12' cy='8' r='1'/></svg></span><span>About</span></h2>
<div>Project repo: <a href='https://github.com/cdomotor-g/ALERT1v3' target='_blank' rel='noopener'>github.com/cdomotor-g/ALERT1v3</a></div>
<div class='muted'>This page mirrors README.md from the running repo.</div>
</div>
<div class='card'><div class='md'>{rendered}</div></div>
</div></body></html>"""


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
            payload = HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/trends':
            payload = TRENDS_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/radio':
            payload = RADIO_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/admin':
            payload = ADMIN_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/about':
            payload = render_about_html().encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/forensics':
            fg = _flowgraph_doc()
            summary_lines = [
                f"file: {fg.get('path','n/a')}",
                f"blocks: {fg.get('block_count',0)}",
                f"connections: {fg.get('connection_count',0)}",
                f"generated: {fg.get('generated_ts','')}",
            ]
            blocks_lines = [f"{b.get('name','?')}  [{b.get('id','?')}]" for b in (fg.get('blocks') or [])]
            conns_lines = [f"{c.get('src_block','?')}:{c.get('src_port','?')} -> {c.get('dst_block','?')}:{c.get('dst_port','?')}" for c in (fg.get('connections') or [])]
            html_body = FORENSICS_HTML.replace('__NAV__', NAV_HTML)
            html_body = html_body.replace('__FG_SUMMARY__', html.escape('\n'.join(summary_lines)))
            html_body = html_body.replace('__FG_BLOCKS__', html.escape('\n'.join(blocks_lines) if blocks_lines else 'none'))
            html_body = html_body.replace('__FG_CONNS__', html.escape('\n'.join(conns_lines) if conns_lines else 'none'))
            payload = html_body.encode('utf-8')
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

        if parsed.path in ['/api/audio_opus', '/api/audio_aac']:
            is_aac = (parsed.path == '/api/audio_aac')
            q = parse_qs(parsed.query)
            try:
                gain = float((q.get('gain', ['1.6'])[0] or '1.6'))
            except Exception:
                gain = 1.6
            gain = max(0.5, min(4.0, gain))
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'audio/aac' if is_aac else 'audio/ogg')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'close')
            self.end_headers()
            arec = subprocess.Popen([
                'arecord','-D','hw:Loopback,1,0','-f','S32_LE','-c','1','-r','48000','-t','raw','-q'
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            ff_cmd = [
                'ffmpeg','-nostdin','-loglevel','error',
                '-f','s32le','-ac','1','-ar','48000','-i','pipe:0',
            ]
            ff_cmd += ['-af', f'volume={gain:.2f}']

            if is_aac:
                ff_cmd += ['-c:a','aac','-b:a','64k','-f','adts','pipe:1']
            else:
                ff_cmd += ['-c:a','libopus','-b:a','32k','-vbr','on','-application','voip','-f','ogg','pipe:1']

            ffm = subprocess.Popen(ff_cmd, stdin=arec.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                while True:
                    chunk = ffm.stdout.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                for p in (ffm, arec):
                    try:
                        p.terminate()
                    except Exception:
                        pass
            return

        if parsed.path == '/api/flowgraph_doc':
            return self._json(_flowgraph_doc())

        if parsed.path == '/api/forensics_bundle':
            q = parse_qs(parsed.query)
            limit = int(q.get('limit', ['300'])[0])
            return self._json(_forensics_bundle(self.store, limit=limit))

        if parsed.path == '/api/rx_agg':
            if RX_AGG_JSON_PATH.exists():
                try:
                    d = json.loads(RX_AGG_JSON_PATH.read_text(encoding='utf-8', errors='replace'))
                    d['source'] = str(RX_AGG_JSON_PATH)
                    return self._json(d)
                except Exception as e:
                    return self._json({'error': f'parse_failed: {e}', 'source': str(RX_AGG_JSON_PATH)}, code=500)
            return self._json({'error': 'not_ready', 'source': str(RX_AGG_JSON_PATH)}, code=404)

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
