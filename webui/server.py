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
import math
import yaml
from datetime import datetime
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, quote
import urllib.request
import csv
import io

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


def _is_valid_rxs_id(v: str) -> bool:
    return bool(re.fullmatch(r'[0-9A-F]{4}', str(v or '').strip().upper()))


def _load_receivers_registry_ids():
    ids = set()
    try:
        if RECEIVERS_REGISTRY_PATH.exists():
            d = json.loads(RECEIVERS_REGISTRY_PATH.read_text(encoding='utf-8', errors='replace'))
            items = d if isinstance(d, list) else d.get('receivers', []) if isinstance(d, dict) else []
            for it in items:
                if not isinstance(it, dict):
                    continue
                rid = str(it.get('rxs_id', '') or '').strip().upper()
                if _is_valid_rxs_id(rid):
                    ids.add(rid)
    except Exception:
        pass
    return ids


def _next_rxs_id():
    used = _load_receivers_registry_ids()
    try:
        if RECEIVER_IDENTITY_PATH.exists():
            d = json.loads(RECEIVER_IDENTITY_PATH.read_text(encoding='utf-8', errors='replace'))
            rid = str((d or {}).get('rxs_id', '')).strip().upper()
            if _is_valid_rxs_id(rid):
                used.add(rid)
    except Exception:
        pass
    for n in range(0x0000, 0x10000):
        rid = f"{n:04X}"
        if rid not in used:
            return rid
    return 'FFFF'


def _load_receiver_identity():
    default = {
        'rxs_id': _next_rxs_id(),
        'name': 'FW-LAB Receiver',
        'location': 'unknown',
        'enabled': True,
    }
    try:
        if RECEIVER_IDENTITY_PATH.exists():
            d = json.loads(RECEIVER_IDENTITY_PATH.read_text(encoding='utf-8', errors='replace'))
            if isinstance(d, dict):
                out = dict(default)
                out.update(d)
                out['rxs_id'] = str(out.get('rxs_id', '')).strip().upper()
                if not _is_valid_rxs_id(out['rxs_id']):
                    out['rxs_id'] = _next_rxs_id()
                out['location'] = str(out.get('location', 'unknown') or 'unknown')
                out['name'] = str(out.get('name', 'FW-LAB Receiver') or 'FW-LAB Receiver')
                out['enabled'] = bool(out.get('enabled', True))
                RECEIVER_IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
                RECEIVER_IDENTITY_PATH.write_text(json.dumps(out, indent=2), encoding='utf-8')
                return out
    except Exception:
        pass
    RECEIVER_IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIVER_IDENTITY_PATH.write_text(json.dumps(default, indent=2), encoding='utf-8')
    return default


def _load_receivers_registry():
    local = _load_receiver_identity()
    default = {'receivers': [
        {
            'rxs_id': local.get('rxs_id', '0000'),
            'name': local.get('name', 'FW-LAB Receiver'),
            'location': local.get('location', 'unknown'),
            'base_url': 'local',
            'enabled': bool(local.get('enabled', True)),
        }
    ]}
    try:
        if RECEIVERS_REGISTRY_PATH.exists():
            d = json.loads(RECEIVERS_REGISTRY_PATH.read_text(encoding='utf-8', errors='replace'))
            if isinstance(d, list):
                d = {'receivers': d}
            if isinstance(d, dict) and isinstance(d.get('receivers'), list):
                out = {'receivers': []}
                seen = set()
                for r in d['receivers']:
                    if not isinstance(r, dict):
                        continue
                    rid = str(r.get('rxs_id', '')).strip().upper()
                    if not _is_valid_rxs_id(rid) or rid in seen:
                        continue
                    seen.add(rid)
                    out['receivers'].append({
                        'rxs_id': rid,
                        'name': str(r.get('name', '') or f'Receiver {rid}'),
                        'location': str(r.get('location', '') or 'unknown'),
                        'base_url': str(r.get('base_url', '') or ''),
                        'enabled': bool(r.get('enabled', True)),
                    })
                if out['receivers']:
                    return out
    except Exception:
        pass
    RECEIVERS_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIVERS_REGISTRY_PATH.write_text(json.dumps(default, indent=2), encoding='utf-8')
    return default

RX_AGG_JSON_PATH = Path('rf_log/rx_agg.json')
STATIONS_CSV_PATH = Path('config/stations.csv')
SENSOR_MAP_CSV_PATH = Path('config/sensor_map.csv')
FILE_DROP_DIR = Path('uploads/file_drop')
PATH_DEFAULTS_PATH = Path('config/path_defaults.json')
RECEIVER_IDENTITY_PATH = Path('config/receiver_identity.json')
RECEIVERS_REGISTRY_PATH = Path('config/receivers_registry.json')
NAV_HTML = f"""
<style>
:root{{--sidebar-w:212px;--sidebar-w-c:64px;--content-gap:14px;}}
.fw-shell{{display:flex;gap:0;}}
.fw-sidebar{{position:fixed;left:0;top:0;bottom:0;width:var(--sidebar-w);background:#0d131a;border-right:1px solid #243243;padding:.75rem .55rem;z-index:1300;transition:width .18s ease;overflow:hidden;}}
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
.fw-mobilebar{{display:none;position:sticky;top:0;z-index:1290;background:#0f141a;border-bottom:1px solid #243243;padding:.45rem .6rem;align-items:center;gap:.6rem;}}
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
<div class='fw-mobilebar'><button class='fw-toggle' id='fwMobileToggle'>☰</button><strong>FW-LAB</strong><select id='fwRxSelect' style='max-width:170px'></select><span class='fw-build'>build {BUILD_STAMP}</span></div>
<div class='fw-shell'>
  <aside class='fw-sidebar' id='fwSidebar'>
    <div class='fw-brand'><span>FW-LAB</span><button class='fw-toggle' id='fwCollapseBtn'>≡</button></div>
    <div class='fw-build' style='padding:0 .45rem .2rem'>build {BUILD_STAMP}</div>
    <div style='padding:0 .45rem .5rem'><select id='fwRxSelectDesk' style='width:100%'></select></div>
    <nav class='fw-nav'>
      <a href='/'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 10.5 12 3l9 7.5'/><path d='M5 9.5V21h14V9.5'/></svg></span><span class='fw-label'>Dashboard</span></a>
      <a href='/packets'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><rect x='4' y='4' width='16' height='16' rx='2'/><path d='M8 9h8M8 13h8M8 17h5'/></svg></span><span class='fw-label'>Packets</span></a>
      <a href='/overview'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='9'/><path d='M8 9h8'/><path d='M8 12h8'/><path d='M8 15h5'/></svg></span><span class='fw-label'>Overview</span></a>
      <a href='/help'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='9'/><path d='M9.1 9a3 3 0 1 1 5.2 2c-.8.7-1.3 1.2-1.3 2.2'/><circle cx='12' cy='17' r='1'/></svg></span><span class='fw-label'>Help</span></a>
      <a href='/radio'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 12h3m12 0h3'/><circle cx='12' cy='12' r='2.5'/><path d='M6.5 8.5a8 8 0 0 1 0 7M17.5 8.5a8 8 0 0 1 0 7'/></svg></span><span class='fw-label'>Radio</span></a>
      <a href='/data'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M4 19h16'/><path d='m6 15 4-4 3 2 5-6'/><path d='m18 7 0 3h-3'/></svg></span><span class='fw-label'>Data</span></a>
      <a href='/path'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M4 20V9'/><path d='M4 9c2.5-1.5 5.5-1.5 8 0s5.5 1.5 8 0v11c-2.5 1.5-5.5 1.5-8 0s-5.5-1.5-8 0'/><circle cx='4' cy='9' r='1.2'/><circle cx='20' cy='9' r='1.2'/></svg></span><span class='fw-label'>Path</span></a>
      <a href='/stations'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M12 3v18'/><path d='M5 8h14'/><path d='M5 16h14'/><circle cx='12' cy='3' r='1.2'/></svg></span><span class='fw-label'>Stations</span></a>
      <a href='/stations-map'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z'/><path d='M9 4v14'/><path d='M15 6v14'/></svg></span><span class='fw-label'>Stations Map</span></a>
      <a href='/trip'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 7h13'/><path d='M3 12h9'/><path d='M3 17h11'/><path d='M17 7l4 4-4 4'/></svg></span><span class='fw-label'>Trip</span></a>
      <a href='/file_drop'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M12 3v12'/><path d='m8 11 4 4 4-4'/><path d='M4 20h16'/></svg></span><span class='fw-label'>File Drop</span></a>
      <a href='/bitflipper'><span class='fw-ico'><svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M8 6h8'/><path d='M8 12h8'/><path d='M8 18h8'/><path d='M5 6h.01M5 12h.01M5 18h.01'/></svg></span><span class='fw-label'>BitFlipper</span></a>
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

  function bindReceiverSelector(reg, info){{
    window.fwReceiversRegistry = reg || {{receivers:[]}};
    window.fwReceiverInfo = info || {{}};

    function findRx(rxsId){{
      var list=(window.fwReceiversRegistry.receivers||[]);
      for(var i=0;i<list.length;i++) if(String(list[i].rxs_id||'')===String(rxsId||'')) return list[i];
      return null;
    }}

    function applySelected(rxsId){{
      window.fwSelectedRxsId = String(rxsId||'');
      window.fwSelectedReceiver = findRx(window.fwSelectedRxsId) || null;
      try {{ window.dispatchEvent(new CustomEvent('fw:receiver-selected', {{ detail: {{ rxs_id: window.fwSelectedRxsId, receiver: window.fwSelectedReceiver }} }})); }} catch(e) {{}}
    }}

    function fill(sel){{
      if(!sel) return;
      sel.innerHTML='';
      (reg.receivers||[]).forEach(function(r){{
        var o=document.createElement('option');
        o.value=r.rxs_id;
        o.textContent=r.rxs_id+' · '+(r.name||'Receiver')+' @ '+(r.location||'unknown');
        sel.appendChild(o);
      }});
      var desired=(localStorage.getItem('fw_selected_rxs_id')||info.rxs_id||'');
      if(!findRx(desired) && (reg.receivers||[]).length) desired=(reg.receivers[0].rxs_id||'');
      sel.value=desired;
      sel.onchange=function(){{
        localStorage.setItem('fw_selected_rxs_id', sel.value||'');
        applySelected(sel.value||'');
      }};
    }}

    fill(document.getElementById('fwRxSelect'));
    fill(document.getElementById('fwRxSelectDesk'));

    var a=document.getElementById('fwRxSelect'), b=document.getElementById('fwRxSelectDesk');
    if(a && b){{
      a.onchange=function(){{ b.value=a.value; localStorage.setItem('fw_selected_rxs_id', a.value||''); applySelected(a.value||''); }};
      b.onchange=function(){{ a.value=b.value; localStorage.setItem('fw_selected_rxs_id', b.value||''); applySelected(b.value||''); }};
    }}

    applySelected((a&&a.value) || (b&&b.value) || info.rxs_id || '');
  }}

  Promise.all([
    fetch('/api/receivers_registry').then(function(r){{return r.json();}}).catch(function(){{return {{receivers:[]}};}}),
    fetch('/api/receiver_info').then(function(r){{return r.json();}}).catch(function(){{return {{rxs_id:''}};}})
  ]).then(function(v){{ bindReceiverSelector(v[0]||{{receivers:[]}}, v[1]||{{}}); }});
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
  <div class='muted' style='margin:-.2rem 0 .55rem'>Live operating view for receiver health and packet flow. Use this page for quick situational awareness before drilling into analysis pages.</div>
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
      Host metrics: <span id='hm-status' class='muted'>n/a</span> · Clock <span id='hm-clock'>-</span> · CPU <span id='hm-cpu'>-</span>% · RAM <span id='hm-mem'>-</span>% · Disk <span id='hm-disk'>-</span>% · Temp <span id='hm-temp'>-</span>°C · Load/core <span id='hm-load'>-</span> · Breaches <span id='hm-breach'>0</span>
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
      <div class='muted small' style='margin-top:.35rem'>Frame bits (graphical)</div>
      <div id='detailBits' class='detail-bits'></div>
      <pre id='detailText'>No event selected.</pre>
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
    <table><thead><tr><th>Time</th><th>Status</th><th>Score</th><th>Ones Ratio</th><th>SNR (dB)</th><th>Conf</th><th>Errs</th><th>Sensor</th><th>Format</th><th>Pair</th><th>Data</th><th>Summary</th></tr></thead><tbody id='rows'></tbody></table>
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
  var isEventsPage = (window.location.pathname === '/events' || window.location.pathname === '/packets');
  if(dataSection && !isEventsPage){ dataSection.style.display='none'; }
  if(tableControlsCard && !isEventsPage){ tableControlsCard.style.display='none'; }
  if(rxSection && isEventsPage){ rxSection.style.display='none'; }
  if(rfControlsSection && isEventsPage){ rfControlsSection.style.display='none'; }
  var status=document.getElementById('status');
  var filtersToggle=document.getElementById('filtersToggle');
  var filtersInner=document.getElementById('filtersInner');
  var rxState=document.getElementById('rx-state');
  function selectedReceiverText(){
    var r=window.fwSelectedReceiver||null;
    if(!r) return 'unknown';
    var t=(r.rxs_id||'')+' · '+(r.name||'Receiver')+' @ '+(r.location||'unknown');
    if(String(r.base_url||'')!=='local') t += ' (remote scaffold)';
    return t;
  }
  window.addEventListener('fw:receiver-selected', function(){
    if(rxState) rxState.textContent = selectedReceiverText();
  });
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
      t.innerHTML = "<span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><rect x='4' y='4' width='16' height='16' rx='2'/><path d='M8 9h8M8 13h8M8 17h5'/></svg></span><span>Packets</span>";
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
    var td=document.createElement('td'); td.colSpan=12;
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
      var sm=g(ev,'sensor_map',null);
      var sensorLabel = sm ? ((g(sm,'site','') && g(sm,'sensor','')) ? (g(sm,'site','')+' - '+g(sm,'sensor','')) : (g(sm,'sensor','') || g(sm,'site','') || sid)) : sid;
      var sidLink = (sid!=='' && sid!==null && sid!==undefined) ? ('<a style="color:#7fc8ff" href="/data?sensor_id='+encodeURIComponent(String(sid))+'&window=24h">'+sensorLabel+'</a>') : '';

      var orHtml = hasErr('signal.bit_balance_extreme') ? ('<span class="bad">'+or+'</span>') : or;
      var snrHtml = hasErr('signal.low_snr_proxy') ? ('<span class="bad">'+snr+'</span>') : snr;
      var fmtHtml = hasErr('decode.invalid_format_id') ? ('<span class="bad">'+g(de,'format_id','')+'</span>') : g(de,'format_id','');
      var sidHtml = hasErr('decode.zero_sensor_id') ? ('<span class="bad">'+sidLink+'</span>') : sidLink;
      var pairId = g(de,'fixed_pair_pattern_id',null);
      var pairHtml = (pairId===null || pairId===undefined || pairId==='') ? '<span class="muted">-</span>' : String(pairId);
      if(hasErr('decode.fixed_pair_mismatch_w1')||hasErr('decode.fixed_pair_mismatch_w2')||hasErr('decode.fixed_pair_mismatch_w3')||hasErr('decode.fixed_pair_mismatch_w4')){
        pairHtml = '<span class="bad">mismatch</span>';
      }
      var summaryHtml = (errN>0) ? ('<span class="warn">'+g(ev,'summary','')+'</span>') : g(ev,'summary','');

      tr.innerHTML='<td>'+fmtTs(g(ev,'ts',''))+'</td><td>'+g(ev,'status','')+'</td><td>'+q+'</td><td>'+orHtml+'</td><td>'+snrHtml+'</td><td>'+c+'</td><td>'+errN+'</td><td>'+sidHtml+'</td><td>'+fmtHtml+'</td><td>'+pairHtml+'</td><td>'+g(de,'data_val','')+'</td><td>'+summaryHtml+'</td>';
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

  function apiBase(){
    var r=window.fwSelectedReceiver||null;
    if(!r || !r.base_url || String(r.base_url)==='local') return '';
    return String(r.base_url).replace(/\/$/, '');
  }
  function apiFetchJson(path){
    var base=apiBase();
    if(!base) return fetch(path).then(function(r){return r.json();});
    return fetch(base+path,{mode:'cors'}).then(function(r){return r.json();});
  }

  function loadEventsSnapshot(){
    apiFetchJson('/api/events?limit=400').then(function(d){
      events=d.events||[];
      source.textContent=g(d,'source','n/a');
      if(isEventsPage){ refreshTailDetail(); }
      render();
      status.textContent='snapshot';
    })['catch'](function(){ status.textContent='offline'; });
  }

  var es=null;
  var remotePollTimer=null;
  function startEventsTransport(){
    if(es){ try{ es.close(); }catch(e){} es=null; }
    if(remotePollTimer){ clearInterval(remotePollTimer); remotePollTimer=null; }
    var base=apiBase();
    if(!base){
      es=new EventSource('/api/live');
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
    } else {
      status.textContent='remote-poll';
      remotePollTimer=setInterval(loadEventsSnapshot, 5000);
    }
  }

  if(isEventsPage){ setTailMode(true); }
  loadEventsSnapshot();
  loadRfConfig();

  function renderHost(m){
    document.getElementById('hm-status').textContent = g(m,'status','n/a');
    var mm=g(m,'metrics',{});
    var t=g(m,'ts','');
    document.getElementById('hm-clock').textContent = t ? fmtTs(t) : '-';
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
      var st=(d.state || 'unknown');
      rxState.textContent = selectedReceiverText()+' · '+st;
      rxState.className = (st==='online') ? 'good' : ((st==='stale') ? 'warn' : 'bad');
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

  window.addEventListener('fw:receiver-selected', function(){
    loadEventsSnapshot();
    startEventsTransport();
    pollReceiver();
  });
  startEventsTransport();

  window.addEventListener('resize', function(){ if(rxChart) rxChart.resize(); if(rxChart24) rxChart24.resize(); });
})();
</script></body></html>"""

def _norm_key(s):
    s = (s or '').strip().strip('"').strip("'").lower()
    return ''.join(ch for ch in s if ch.isalnum() or ch == '_')


def _norm_val(s):
    return (s or '').strip().strip('"').strip("'")


def _parse_stations_csv_text(text, limit=5000):
    lines = [ln for ln in (text or '').splitlines() if ln.strip()]
    if not lines:
        return []
    sample = '\n'.join(lines[:30])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
    except Exception:
        dialect = csv.excel
    raw_rows = list(csv.reader(lines, dialect))
    if not raw_rows:
        return []

    # Find header row by looking for lat/lon-like column names.
    header_idx = 0
    for i, row in enumerate(raw_rows[:12]):
        keys = [_norm_key(c) for c in row]
        if any(k in keys for k in ['latitude', 'lat']) and any(k in keys for k in ['longitude', 'lon', 'lng']):
            header_idx = i
            break
        if 'unitname' in keys and any(k in keys for k in ['latitude', 'longitude']):
            header_idx = i
            break

    headers = [_norm_key(c) or f'col{j+1}' for j, c in enumerate(raw_rows[header_idx])]
    out = []
    for row in raw_rows[header_idx+1:]:
        if len(out) >= limit:
            break
        if not any((c or '').strip() for c in row):
            continue
        rec = {}
        for j, h in enumerate(headers):
            rec[h] = _norm_val(row[j]) if j < len(row) else ''
        out.append(rec)
    return out


def _load_stations(limit=5000):
    # Prefer centralized metadata catalog when present.
    try:
        cat = load_meta_catalog('config/meta_catalog.json')
        rows = []
        for s in (cat.get('stations') or []):
            if not isinstance(s, dict):
                continue
            rows.append({
                'unitid': str(s.get('bom_stn', '') or s.get('station_key', '') or '').strip(),
                'unitname': str(s.get('name', '') or '').strip(),
                'name': str(s.get('name', '') or '').strip(),
                'enabled': '1' if bool(s.get('enabled', True)) else '0',
                'latitude': str(s.get('lat', '') or '').strip(),
                'longitude': str(s.get('lon', '') or '').strip(),
                'elevation': str(s.get('elevation_m', '') or '').strip(),
                'arro_site_id': str(s.get('arro_site_id', '') or '').strip(),
                'sensor_types': str(s.get('sensor_types', '') or '').strip(),
                'sensor_ids': str(s.get('sensor_ids', '') or '').strip(),
                'device_ids': str(s.get('device_ids', '') or '').strip(),
                'kml_name': str(s.get('kml_name', '') or '').strip(),
                'source': 'meta_catalog',
                'station_key': str(s.get('station_key', '') or '').strip(),
            })
        if rows:
            return rows[:max(1, min(limit, 200000))]
    except Exception:
        pass

    src = Path('config/stations_catalog.csv') if Path('config/stations_catalog.csv').exists() else STATIONS_CSV_PATH
    if not src.exists():
        return []
    try:
        txt = src.read_text(encoding='utf-8', errors='replace')
        rows = _parse_stations_csv_text(txt, limit=limit)
        if src.name == 'stations_catalog.csv':
            return rows
        return _merge_stations_with_sensor_map(rows)
    except Exception:
        return []


def _station_lat_lon(r):
    lat = None
    lon = None
    for lk in ['lat', 'latitude', 'sitelat', 'y']:
        if lk in r and r[lk] != '':
            try:
                lat = float(r[lk]); break
            except Exception:
                pass
    for ok in ['lon', 'longitude', 'lng', 'sitelon', 'x']:
        if ok in r and r[ok] != '':
            try:
                lon = float(r[ok]); break
            except Exception:
                pass
    return lat, lon


def _station_name(r, idx):
    for nk in ['name', 'unitname', 'station', 'site', 'id', 'unitid', 'stationid']:
        if nk in r and r[nk]:
            return r[nk]
    return f'station_{idx+1}'


def _pairs_within_km(rows, max_km=100.0, limit=2000):
    pts = []
    for i, r in enumerate(rows):
        lat, lon = _station_lat_lon(r)
        if lat is None or lon is None:
            continue
        pts.append((i, _station_name(r, i), lat, lon))
    out = []
    for a in range(len(pts)):
        ia, na, la, loa = pts[a]
        for b in range(a+1, len(pts)):
            ib, nb, lb, lob = pts[b]
            d = _haversine_km(la, loa, lb, lob)
            if d <= max_km:
                out.append({'a_index': ia, 'a_name': na, 'b_index': ib, 'b_name': nb, 'distance_km': round(d, 3)})
                if len(out) >= limit:
                    return out
    out.sort(key=lambda x: x['distance_km'])
    return out


def _load_path_defaults():
    if not PATH_DEFAULTS_PATH.exists():
        return {}
    try:
        d = json.loads(PATH_DEFAULTS_PATH.read_text(encoding='utf-8', errors='replace'))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_path_defaults(d):
    if not isinstance(d, dict):
        raise ValueError('defaults must be object')
    PATH_DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH_DEFAULTS_PATH.write_text(json.dumps(d, indent=2), encoding='utf-8')


def _norm_hdr(s):
    s = (s or '').strip().lower()
    return ''.join(ch for ch in s if ch.isalnum() or ch == '_')


def _looks_like_sensor_map_csv(text: str):
    try:
        lines = [ln for ln in (text or '').splitlines() if ln.strip()]
        if not lines:
            return False
        row = next(csv.reader([lines[0]]))
        hs = {_norm_hdr(h) for h in row}
        required = {'site', 'siteid', 'sensor', 'sensorid', 'site_id', 'device_id'}
        # Allow either compact or underscored variants for site/sensor ids.
        has = set(hs)
        has_siteid = ('siteid' in has) or ('site_id' in has)
        has_sensorid = ('sensorid' in has) or ('sensor_id' in has)
        return ('site' in has) and has_siteid and ('sensor' in has) and has_sensorid and ('device_id' in has)
    except Exception:
        return False


def _load_sensor_map(limit=50000):
    out = {}
    if not SENSOR_MAP_CSV_PATH.exists():
        return out
    try:
        with SENSOR_MAP_CSV_PATH.open('r', encoding='utf-8', errors='replace', newline='') as fh:
            rdr = csv.DictReader(fh)
            for i, r in enumerate(rdr):
                if i >= limit:
                    break
                rn = {_norm_hdr(k): (v or '').strip() for k, v in (r or {}).items()}
                site = (rn.get('site') or '').strip()
                sensor = (rn.get('sensor') or '').strip()
                sid = (rn.get('sensorid') or rn.get('sensor_id') or '').strip()
                bom = (rn.get('siteid') or rn.get('site_id') or '').strip()
                arro_site = (rn.get('site_id') or '').strip()
                device_id = (rn.get('device_id') or '').strip()
                alert1_id = ''
                if sid:
                    parts = sid.split('.')
                    alert1_id = (parts[-1] if parts else sid).strip()
                if alert1_id:
                    out[str(alert1_id)] = {
                        'site': site,
                        'site_id_bom': bom,
                        'sensor': sensor,
                        'sensor_id': sid,
                        'alert1_id': alert1_id,
                        'arro_site_id': arro_site,
                        'arro_device_id': device_id,
                    }
    except Exception:
        return {}
    return out


def _merge_stations_with_sensor_map(rows):
    sm = _load_sensor_map(limit=200000)
    if not sm:
        return rows

    by_bom = {}
    sensors_by_bom = {}
    for m in sm.values():
        bom = str(m.get('site_id_bom', '') or '').strip()
        if not bom:
            continue
        by_bom.setdefault(bom, m)
        sensors_by_bom.setdefault(bom, set()).add(str(m.get('sensor', '') or '').strip())

    out = []
    for r in (rows or []):
        rec = dict(r)
        uid = str(rec.get('unitid', '') or rec.get('id', '') or '').strip()
        m = by_bom.get(uid)
        if m:
            site = str(m.get('site', '') or '').strip()
            if site:
                rec['unitname'] = site  # fix truncation/incomplete names from legacy CSV exports
                rec['name'] = site
            rec['site_id_bom'] = uid
            rec['arro_site_id'] = str(m.get('arro_site_id', '') or '').strip()
            ss = sorted(s for s in sensors_by_bom.get(uid, set()) if s)
            if ss:
                rec['sensor_types'] = ', '.join(ss)
        out.append(rec)
    return out


def _write_stations_master(rows):
    try:
        p = Path('config/stations_master.csv')
        p.parent.mkdir(parents=True, exist_ok=True)
        keys = ['unitid', 'unitname', 'latitude', 'longitude', 'elevation', 'site_id_bom', 'arro_site_id', 'sensor_types']
        with p.open('w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow({k: (r.get(k, '') if isinstance(r, dict) else '') for k in keys})
    except Exception:
        pass


def _save_stations_rows(rows):
    if not isinstance(rows, list):
        raise ValueError('rows must be list')
    keys = []
    seen = set()
    preferred = ['unitid', 'unitname', 'enabled', 'latitude', 'longitude', 'elevation']
    for k in preferred:
        seen.add(k); keys.append(k)
    for r in rows:
        if not isinstance(r, dict):
            continue
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                keys.append(k)
    STATIONS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATIONS_CSV_PATH.open('w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            row = {k: str(r.get(k, '') or '') for k in keys}
            w.writerow(row)


PATH_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Path</title>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,button,select{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}a{color:#7fc8ff}.grid{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:.5rem}.muted{color:#9fb0c3}.good{color:#6dd17c}.warn{color:#f2c14e}.bad{color:#f36f6f}#profile{height:320px}#pathMap{height:320px;border:1px solid #2a3948;border-radius:8px}@media(max-width:860px){.grid{grid-template-columns:1fr 1fr}input,button,select{min-height:40px;font-size:16px}}</style>
<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'/>
<script src='https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'></script>
<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script></head><body><div class='page'>
<h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M4 20V9'/><path d='M4 9c2.5-1.5 5.5-1.5 8 0s5.5 1.5 8 0v11c-2.5 1.5-5.5 1.5-8 0s-5.5-1.5-8 0'/><circle cx='4' cy='9' r='1.2'/><circle cx='20' cy='9' r='1.2'/></svg></span><span>Path</span></h2>
<div class='muted' style='margin:-.2rem 0 .55rem'>RF path analysis workspace for terrain, Fresnel clearance, and link budget checks between candidate sites. Use Compare to test scenarios and defaults for repeatable planning.</div>
__NAV__
<div class='card grid'>
  <div style='grid-column:1/-1' class='muted'>Optional: pick known stations (type to filter)</div>
  <label style='grid-column:span 2'><span title='Type station name and pick from list to auto-fill TX lat/lon.'>TX Station ⓘ</span><br><input id='txStation' list='stationsList' placeholder='Start typing station name...'></label>
  <label style='grid-column:span 2'><span title='Type station name and pick from list to auto-fill RX lat/lon.'>RX Station ⓘ</span><br><input id='rxStation' list='stationsList' placeholder='Start typing station name...'></label>
  <datalist id='stationsList'></datalist>
  <label><span title='Transmitter latitude in decimal degrees. Example: -27.4698'>TX Lat ⓘ</span><br><input id='txLat' value='-27.4698'></label>
  <label><span title='Transmitter longitude in decimal degrees. Example: 153.0251'>TX Lon ⓘ</span><br><input id='txLon' value='153.0251'></label>
  <label><span title='Antenna height above local ground level (meters).'>TX AGL m ⓘ</span><br><input id='txH' value='10'></label>
  <label><span title='Transmit power at radio output in dBm.'>TX Pwr dBm ⓘ</span><br><input id='txP' value='37'></label>
  <label><span title='Receiver latitude in decimal degrees.'>RX Lat ⓘ</span><br><input id='rxLat' value='-27.56'></label>
  <label><span title='Receiver longitude in decimal degrees.'>RX Lon ⓘ</span><br><input id='rxLon' value='152.98'></label>
  <label><span title='Receiver antenna height above local ground (meters).'>RX AGL m ⓘ</span><br><input id='rxH' value='8'></label>
  <label><span title='RF center frequency in MHz. Example: 173.9'>Freq MHz ⓘ</span><br><input id='freq' value='173.9'></label>
  <label><span title='Transmitter antenna gain in dBi.'>TX Gain dBi ⓘ</span><br><input id='txG' value='3'></label>
  <label><span title='Receiver antenna gain in dBi.'>RX Gain dBi ⓘ</span><br><input id='rxG' value='3'></label>
  <label><span title='Aggregate transmitter-side losses (cable/connectors/etc) in dB.'>TX Loss dB ⓘ</span><br><input id='txL' value='1.5'></label>
  <label><span title='Aggregate receiver-side losses (cable/connectors/etc) in dB.'>RX Loss dB ⓘ</span><br><input id='rxL' value='1.5'></label>
  <label><span title='Receiver sensitivity threshold in dBm used for fade margin.'>RX Sens dBm ⓘ</span><br><input id='rxS' value='-110'></label>
  <label><span title='Optional measured receive level for parity comparison (dBm).'>Measured RX dBm ⓘ</span><br><input id='rxM' value=''></label>
  <label><span title='Path profile sample spacing in meters.'>Step m ⓘ</span><br><input id='step' value='100'></label>
  <label><span title='Propagation mode. FSPL is baseline; diffraction proxy adds interim obstruction penalty.'>Model ⓘ</span><br><select id='model'><option value='fspl_mvp'>FSPL baseline</option><option value='fspl_diffraction_proxy' selected>FSPL + diffraction proxy</option></select></label>
  <label><span title='Flat terrain elevation baseline (m ASL) when no terrain profile/provider is used.'>Terrain base m ASL ⓘ</span><br><input id='tBase' value='0'></label>
  <label><span title='Terrain source. OpenTopoData uses public SRTM API (best-effort).'>Terrain provider ⓘ</span><br><select id='tProvider'><option value='flat'>flat</option><option value='opentopodata' selected>OpenTopoData SRTM</option></select></label>
  <div style='grid-column:1/-1' class='muted small'>Optional terrain profile override (comma-separated m ASL):</div>
  <div style='grid-column:1/-1'><input id='tOverride' placeholder='e.g. 40,40.2,41.1,42.0' style='width:100%'></div>
  <label><span title='Optional scenario name for save/load.'>Scenario ⓘ</span><br><input id='scName' placeholder='e.g. SiteA-SiteB-173.9'></label>
  <div style='align-self:end'><button id='saveSc'>Save scenario</button> <button id='loadSc'>Load scenario</button></div>
  <div style='align-self:end'><button id='saveDef'>Save as defaults</button> <button id='loadDef'>Load defaults</button></div>
  <div style='align-self:end'><button id='run'>Analyze</button> <button id='export'>Export JSON</button></div>
</div>
<div class='card'>Distance: <span id='dist'>-</span> km · Path loss: <span id='loss'>-</span> dB · Rx: <span id='rx'>-</span> dBm · Fade margin: <span id='margin'>-</span> dB (<span id='mclass'>-</span>)</div>
<div class='card'><div class='muted'>Top-down path map (TX→RX)</div><div id='pathMap'></div></div>
<div class='card'><div id='profile'></div></div>
<div class='card'><div class='muted'>Radio Mobile parity worksheet (copy to compare)</div><pre id='parity' style='white-space:pre-wrap'>run Analyze to populate</pre></div>
<div class='card'><div class='muted'>Assumptions / warnings</div><pre id='warn' style='white-space:pre-wrap'></pre></div>
<script>
(function(){
  function v(id){ return Number(document.getElementById(id).value); }
  function gv(o,k,d){ return (o && o[k]!==undefined && o[k]!==null) ? o[k] : d; }
  function getReq(){
    var to=document.getElementById('tOverride').value.trim();
    var ov=null;
    if(to){ ov=to.split(',').map(function(x){return Number(String(x).trim());}).filter(function(x){return isFinite(x);}); if(!ov.length) ov=null; }
    var m=document.getElementById('rxM').value.trim();
    return {schema:'fwlab.path.request.v1',tx:{lat:v('txLat'),lon:v('txLon'),antenna_agl_m:v('txH')},rx:{lat:v('rxLat'),lon:v('rxLon'),antenna_agl_m:v('rxH')},rf:{frequency_mhz:v('freq'),tx_power_dbm:v('txP'),tx_antenna_gain_dbi:v('txG'),rx_antenna_gain_dbi:v('rxG'),tx_system_loss_db:v('txL'),rx_system_loss_db:v('rxL'),rx_sensitivity_dbm:v('rxS')},measured:{rx_dbm:(m===''?null:Number(m))},model:{mode:document.getElementById('model').value},sampling:{profile_step_m:v('step'),terrain_base_m_asl:v('tBase'),terrain_provider:document.getElementById('tProvider').value,terrain_profile_m_asl:ov},stations:{tx_name:(document.getElementById('txStation').value||'').trim(),rx_name:(document.getElementById('rxStation').value||'').trim()}};
  }
  function setField(id,val){ if(val!==undefined && val!==null) document.getElementById(id).value=String(val); }
  function applyReq(s){
    var tx=s.tx||{}, rx=s.rx||{}, rf=s.rf||{}, md=s.model||{}, sp=s.sampling||{}, st=s.stations||{};
    setField('txLat',tx.lat); setField('txLon',tx.lon); setField('txH',tx.antenna_agl_m);
    setField('rxLat',rx.lat); setField('rxLon',rx.lon); setField('rxH',rx.antenna_agl_m);
    setField('freq',rf.frequency_mhz); setField('txP',rf.tx_power_dbm); setField('txG',rf.tx_antenna_gain_dbi); setField('rxG',rf.rx_antenna_gain_dbi);
    setField('txL',rf.tx_system_loss_db); setField('rxL',rf.rx_system_loss_db); setField('rxS',rf.rx_sensitivity_dbm);
    setField('rxM',(s.measured||{}).rx_dbm);
    setField('step',sp.profile_step_m); setField('tBase',sp.terrain_base_m_asl);
    document.getElementById('model').value = md.mode || 'fspl_diffraction_proxy';
    document.getElementById('tProvider').value = sp.terrain_provider || 'opentopodata';
    document.getElementById('tOverride').value = Array.isArray(sp.terrain_profile_m_asl) ? sp.terrain_profile_m_asl.join(',') : '';
    setField('txStation', st.tx_name || '');
    setField('rxStation', st.rx_name || '');
  }
  var chart=echarts.init(document.getElementById('profile'));
  var stationsByName={};
  function loadStationsCatalog(){
    fetch('/api/stations/catalog?limit=20000').then(function(r){ return r.json(); }).then(function(d){
      var list=document.getElementById('stationsList');
      if(!list) return;
      list.innerHTML='';
      stationsByName={};
      (d.stations||[]).forEach(function(s){
        if(!s || !s.name) return;
        stationsByName[s.name]=s;
        var o=document.createElement('option');
        o.value=s.name;
        o.label=s.name+' ('+s.lat+', '+s.lon+')';
        list.appendChild(o);
      });
    }).catch(function(){});
  }
  function applyStation(prefix){
    var nm=(document.getElementById(prefix+'Station').value||'').trim();
    var s=stationsByName[nm];
    if(!s) return;
    setField(prefix+'Lat', s.lat);
    setField(prefix+'Lon', s.lon);
    if(document.getElementById('scName') && !document.getElementById('scName').value){
      var other=(prefix==='tx'?'rx':'tx');
      var on=(document.getElementById(other+'Station').value||'').trim();
      if(on) document.getElementById('scName').value=(prefix==='tx'?nm:on)+'-'+(prefix==='tx'?on:nm);
    }
  }
  var lastResult=null;
  var map=null, mapLine=null, txMark=null, rxMark=null, txDir=null;
  function drawMap(req){
    if(!(window.L && document.getElementById('pathMap'))) return;
    var tx=[req.tx.lat, req.tx.lon], rx=[req.rx.lat, req.rx.lon];
    if(!map){
      map=L.map('pathMap',{zoomControl:true});
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);
    }
    if(mapLine) map.removeLayer(mapLine);
    if(txMark) map.removeLayer(txMark);
    if(rxMark) map.removeLayer(rxMark);
    if(txDir) map.removeLayer(txDir);

    mapLine=L.polyline([tx,rx],{color:'#6fa8ff',weight:3}).addTo(map);
    txMark=L.circleMarker(tx,{radius:6,color:'#ff6b6b',fillColor:'#ff6b6b',fillOpacity:0.9}).addTo(map).bindTooltip('TX',{permanent:true,direction:'top'});
    rxMark=L.circleMarker(rx,{radius:6,color:'#5bbf7a',fillColor:'#5bbf7a',fillOpacity:0.9}).addTo(map).bindTooltip('RX',{permanent:true,direction:'top'});

    // TX direction arrow toward RX
    var latStep=(rx[0]-tx[0])*0.18, lonStep=(rx[1]-tx[1])*0.18;
    var p2=[tx[0]+latStep, tx[1]+lonStep];
    txDir=L.polyline([tx,p2],{color:'#ff8a8a',weight:4,opacity:0.95}).addTo(map);

    map.fitBounds(L.latLngBounds([tx,rx]).pad(0.35));
    setTimeout(function(){ map.invalidateSize(); }, 30);
  }

  function draw(profile){
    var d=(profile.distance_m||[]).map(function(x){ return Number(x)||0; });
    var t=(profile.terrain_m_asl||[]).map(function(x){ return Number(x)||0; });
    var l=(profile.los_m_asl||[]).map(function(x){ return Number(x)||0; });
    var f=(profile.fresnel60_radius_m||[]).map(function(x){ return Number(x)||0; });
    var maxF=0;
    for(var fi=0;fi<f.length;fi++){ if(f[fi]>maxF) maxF=f[fi]; }
    var visScale = (maxF>0 && maxF<2.0) ? 10 : 1; // short links: make guides visible
    var minVisRadius = (maxF>0) ? 3.0 : 0.0; // display floor so guides are always visible
    function band(mult){
      var up=[], lo=[];
      for(var i=0;i<l.length;i++){
        var raw = ((f[i]||0)*mult*visScale);
        var rr = (raw>0) ? Math.max(raw, minVisRadius) : 0;
        up.push((l[i]||0)+rr);
        lo.push((l[i]||0)-rr);
      }
      return {up:up, lo:lo};
    }
    var b20=band(0.2), b40=band(0.4), b60=band(0.6);
    var hasF = f.some(function(x){ return x>0.0001; });
    chart.setOption({
      animation:false,
      grid:{left:46,right:12,top:20,bottom:30},
      tooltip:{trigger:'axis'},
      legend:{textStyle:{color:'#b6c2cf'}},
      xAxis:{type:'category',data:d.map(function(x){return (x/1000).toFixed(2);}),name:'km'},
      yAxis:{type:'value',name:'m'},
      series:[
        {name:'terrain',type:'line',data:t,symbol:'none',lineStyle:{color:'#5bbf7a',width:2},z:2},
        {name:'F1 +20%'+(visScale>1?' (vis x'+visScale+')':''),type:'line',data:b20.up,symbol:'none',lineStyle:{color:'#ffd166',type:'dashed',opacity:0.85,width:1.6},z:3},
        {name:'F1 -20%'+(visScale>1?' (vis x'+visScale+')':''),type:'line',data:b20.lo,symbol:'none',lineStyle:{color:'#ffd166',type:'dashed',opacity:0.85,width:1.6},z:3},
        {name:'F1 +40%'+(visScale>1?' (vis x'+visScale+')':''),type:'line',data:b40.up,symbol:'none',lineStyle:{color:'#ffbf69',type:'dashed',opacity:0.9,width:1.8},z:3},
        {name:'F1 -40%'+(visScale>1?' (vis x'+visScale+')':''),type:'line',data:b40.lo,symbol:'none',lineStyle:{color:'#ffbf69',type:'dashed',opacity:0.9,width:1.8},z:3},
        {name:'F1 +60%'+(visScale>1?' (vis x'+visScale+')':''),type:'line',data:b60.up,symbol:'none',lineStyle:{color:'#ff9f1c',type:'solid',opacity:0.98,width:2.0},z:4},
        {name:'F1 -60%'+(visScale>1?' (vis x'+visScale+')':''),type:'line',data:b60.lo,symbol:'none',lineStyle:{color:'#ff9f1c',type:'solid',opacity:0.98,width:2.0},areaStyle:{color:'rgba(255,159,28,0.16)'},z:4},
        {name:'los',type:'line',data:l,symbol:'none',lineStyle:{color:'#ff8a8a',width:2},z:5}
      ]
    }, true);
    if(!hasF){ document.getElementById('warn').textContent='warning: fresnel radii unavailable in profile output'; }
    else if(visScale>1){ document.getElementById('warn').textContent='note: short path detected; Fresnel guides shown with visual scale x'+visScale+' (numbers in worksheet are unchanged)'; }
  }
  function parityText(req,d){
    var s=d.summary||{}, b=d.budget||{}, a=d.assumptions||{};
    return [
      '=== FW-LAB Path Analysis (for Radio Mobile comparison) ===',
      'TX lat,lon: '+req.tx.lat+', '+req.tx.lon,
      'RX lat,lon: '+req.rx.lat+', '+req.rx.lon,
      'TX/RX antenna AGL m: '+req.tx.antenna_agl_m+' / '+req.rx.antenna_agl_m,
      'Frequency MHz: '+req.rf.frequency_mhz,
      'TX power dBm: '+req.rf.tx_power_dbm,
      'TX/RX antenna gain dBi: '+req.rf.tx_antenna_gain_dbi+' / '+req.rf.rx_antenna_gain_dbi,
      'TX/RX system losses dB: '+req.rf.tx_system_loss_db+' / '+req.rf.rx_system_loss_db,
      'RX sensitivity dBm: '+req.rf.rx_sensitivity_dbm,
      'Distance km: '+s.distance_km,
      'FSPL dB: '+b.fspl_db,
      'Diffraction proxy dB: '+b.diffraction_proxy_db,
      'Total path loss dB: '+s.path_loss_db,
      'Predicted RX dBm: '+s.predicted_rx_dbm,
      'Fade margin dB: '+s.fade_margin_db+' ('+s.margin_class+')',
      'Model mode: '+a.propagation_model,
      'Terrain mode: '+a.terrain_mode,
      'Fresnel60 min clearance m: '+a.fresnel60_min_clearance_m,
      (d.parity ? ('Measured RX dBm: '+d.parity.measured_rx_dbm+'\\nDelta (pred-measured) dB: '+d.parity.delta_db+'\\nFit class: '+d.parity.fit_class) : 'Measured RX dBm: (not provided)')
    ].join('\\n');
  }

  function run(){
    document.getElementById('warn').textContent='running...';
    var req=getReq();
    fetch('/api/path/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)}).then(function(r){return r.json();}).then(function(d){
      lastResult=d;
      var s=d.summary||{};
      drawMap(req);
      document.getElementById('dist').textContent=gv(s,'distance_km','-');
      document.getElementById('loss').textContent=gv(s,'path_loss_db','-')+' (fspl '+gv(s,'fspl_db','-')+' + diff '+gv(s,'diffraction_proxy_db','0')+')';
      document.getElementById('rx').textContent=gv(s,'predicted_rx_dbm','-');
      document.getElementById('margin').textContent=gv(s,'fade_margin_db','-');
      var mc=document.getElementById('mclass'); var mcls=gv(s,'margin_class','-');
      mc.textContent=mcls; mc.className=mcls==='good'?'good':(mcls==='marginal'?'warn':'bad');
      var prof=(d.profile||{});
      draw(prof);
      var warn=(d.warnings||[]).join('\\n');
      var asm=d.assumptions||{};
      var fres=(prof.fresnel60_radius_m||[]).map(function(x){ return Number(x)||0; });
      var maxF=0; for(var i=0;i<fres.length;i++){ if(fres[i]>maxF) maxF=fres[i]; }
      var note=(maxF>0) ? ('\\nvisual note: Fresnel guides are display-scaled (auto x'+((maxF<2.0)?'10':'1')+', min envelope ±3m) for readability; worksheet values unchanged') : '';
      document.getElementById('warn').textContent=(warn||'none')+note+'\\n'+JSON.stringify(asm,null,2);
      document.getElementById('parity').textContent = parityText(req,d);
    }).catch(function(e){ document.getElementById('warn').textContent='analyze failed: '+e; });
  }
  var txStationEl=document.getElementById('txStation');
  var rxStationEl=document.getElementById('rxStation');
  if(txStationEl){ txStationEl.addEventListener('change', function(){ applyStation('tx'); }); txStationEl.addEventListener('input', function(){ applyStation('tx'); }); }
  if(rxStationEl){ rxStationEl.addEventListener('change', function(){ applyStation('rx'); }); rxStationEl.addEventListener('input', function(){ applyStation('rx'); }); }

  document.getElementById('run').addEventListener('click',run);
  document.getElementById('saveSc').addEventListener('click', function(){
    var name=document.getElementById('scName').value.trim()||('scenario-'+Date.now());
    var all={};
    try{ all=JSON.parse(localStorage.getItem('fwlab_path_scenarios')||'{}'); }catch(e){ all={}; }
    all[name]=getReq();
    localStorage.setItem('fwlab_path_scenarios', JSON.stringify(all));
    document.getElementById('warn').textContent='saved scenario: '+name;
  });
  document.getElementById('loadSc').addEventListener('click', function(){
    var name=document.getElementById('scName').value.trim();
    var all={};
    try{ all=JSON.parse(localStorage.getItem('fwlab_path_scenarios')||'{}'); }catch(e){ all={}; }
    var s=all[name];
    if(!s){ document.getElementById('warn').textContent='scenario not found: '+name; return; }
    applyReq(s);
    document.getElementById('warn').textContent='loaded scenario: '+name;
  });
  document.getElementById('saveDef').addEventListener('click', function(){
    var req=getReq();
    fetch('/api/path/defaults',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)})
      .then(function(r){ return r.json(); })
      .then(function(d){ document.getElementById('warn').textContent = d.ok ? 'saved global path defaults' : ('save defaults failed: '+(d.error||'unknown')); })
      .catch(function(e){ document.getElementById('warn').textContent='save defaults failed: '+e; });
  });
  document.getElementById('loadDef').addEventListener('click', function(){
    fetch('/api/path/defaults').then(function(r){ return r.json(); }).then(function(d){
      if(!d || !d.defaults){ document.getElementById('warn').textContent='no saved defaults yet'; return; }
      applyReq(d.defaults);
      document.getElementById('warn').textContent='loaded global path defaults';
    }).catch(function(e){ document.getElementById('warn').textContent='load defaults failed: '+e; });
  });

  document.getElementById('export').addEventListener('click', function(){
    if(!lastResult){ document.getElementById('warn').textContent='nothing to export yet'; return; }
    var blob=new Blob([JSON.stringify(lastResult,null,2)],{type:'application/json;charset=utf-8'});
    var url=URL.createObjectURL(blob); var a=document.createElement('a');
    a.href=url; a.download='path_analysis_result.json'; a.click(); URL.revokeObjectURL(url);
  });
  loadStationsCatalog();
  fetch('/api/path/defaults').then(function(r){ return r.json(); }).then(function(d){
    if(d && d.defaults){ applyReq(d.defaults); }
    run();
  }).catch(function(){ run(); });
  window.addEventListener('resize', function(){ chart.resize(); if(map) map.invalidateSize(); });
})();
</script></div></body></html>"""

STATIONS_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Stations</title>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,button{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.35rem;max-width:100%;box-sizing:border-box}.muted{color:#9fb0c3}.row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}.mini{font-size:.9em}.num{width:8.5rem}.table-wrap{overflow:auto}.st-table{width:100%;min-width:980px;border-collapse:collapse}.st-table th,.st-table td{padding:.35rem;border-bottom:1px solid #243243;text-align:left}.cards{display:none}.st-card{border:1px solid #2a3948;border-radius:8px;margin:.5rem 0;background:#111a22}.st-card summary{cursor:pointer;padding:.6rem .65rem;list-style:none}.st-card summary::-webkit-details-marker{display:none}.st-card[open] summary{border-bottom:1px solid #243243}.st-body{padding:.6rem}.st-card .grid{display:grid;grid-template-columns:1fr 1fr;gap:.4rem}.st-card input{width:100%;box-sizing:border-box}.stack{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}.stack .grow{flex:1 1 260px}.filter-card{padding:.45rem .6rem}@media(max-width:900px){.table-wrap{display:none}.cards{display:block}.row,.stack{flex-direction:column;align-items:stretch}input,button{width:100%;min-height:40px;font-size:16px}.filter-card{padding:.35rem .55rem}.page{padding:.7rem}}</style></head><body><div class='page'>
<h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M12 3v18'/><path d='M5 8h14'/><path d='M5 16h14'/><circle cx='12' cy='3' r='1.2'/></svg></span><span>Stations</span></h2>
<div class='muted' style='margin:-.2rem 0 .55rem'>Editable station registry with BoM station numbers, coordinates, and metadata used across maps and planning tools. Use this page to search, review, and maintain station records.</div>
__NAV__
<div class='card stack'>
  <input id='csvFile' type='file' accept='.csv,text/csv'>
  <button id='upload'>Upload CSV</button>
  <button id='reload'>Reload</button>
  <a href='/stations-map' style='color:#7fc8ff'>Open map view →</a>
  <span id='msg' class='muted'></span>
</div>
<div class='card filter-card'>
  <input id='q' class='grow' placeholder='Type to filter stations...'>
</div>
<div class='card mini'>Stations loaded: <span id='count'>0</span> · Showing: <span id='shown'>0</span></div>
<div class='card' id='streetCard' style='display:none'><div id='streetTitle' style='margin-bottom:.35rem'></div><img id='streetImg' alt='Street View' style='width:100%;max-height:260px;object-fit:cover;border:1px solid #2a3948;border-radius:6px'><div id='streetNote' class='muted' style='margin-top:.25rem'></div></div>
<div class='card table-wrap'><table class='st-table'><thead><tr><th>#</th><th>BoM_Stn#</th><th>Name</th><th>Enabled</th><th>Lat</th><th>Lon</th><th>Elevation</th><th>Sensor Types</th><th>Sensor IDs</th><th>ARRO site_id</th><th>device_ids</th><th>KML Name</th><th>Source</th><th>Map</th><th>ARRO</th><th>Icon</th><th>Style</th><th>Locked</th><th>Directions</th><th>Street</th><th></th></tr></thead><tbody id='rows'></tbody></table></div>
<div class='card cards' id='cards'></div>
<script>
(function(){
  var all=[];
  function esc(s){ return String(s||'').replace(/[&<>\"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function firstCsv(v){ return String(v||'').split(',').map(function(x){return x.trim();}).filter(Boolean)[0]||''; }
  function arroUrl(r){
    var siteId=String(r.arro_site_id||'').trim();
    var devId=firstCsv(r.device_ids||'');
    if(!siteId) return '';
    var u='https://contrail-bom.onerain.au/administration/sensor/details/?site_id='+encodeURIComponent(siteId);
    if(devId) u += '&device_id='+encodeURIComponent(devId);
    return u;
  }
  function load(){
    fetch('/api/stations/rows?limit=50000').then(r=>r.json()).then(d=>{
      all=d.rows||[];
      document.getElementById('count').textContent = d.count||0;
      render();
    }).catch(function(){ document.getElementById('msg').textContent='failed to load stations'; });
  }
  function match(r, q){
    if(!q) return true;
    q=q.toLowerCase();
    return [r.name,r.unitname,r.latitude,r.longitude,r.elevation,r.unitid,r.enabled,r.icon,r.style,r.locked,r.sensor_types,r.sensor_ids,r.arro_site_id,r.device_ids,r.kml_name,r.source].some(function(v){ return String(v||'').toLowerCase().indexOf(q)>=0; });
  }
  function savePatch(patch, idx){
    fetch('/api/stations/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(patch)})
      .then(function(x){ return x.json(); })
      .then(function(d){ document.getElementById('msg').textContent = d.ok ? ('saved station #'+idx) : ('save failed: '+(d.error||'unknown')); if(d.ok) load(); })
      .catch(function(){ document.getElementById('msg').textContent='save failed'; });
  }
  function streetUrl(lat,lon,w,h){
    return 'https://maps.googleapis.com/maps/api/streetview?size='+(w||640)+'x'+(h||320)+'&location='+encodeURIComponent(lat+','+lon)+'&fov=90&pitch=0&source=outdoor';
  }
  function streetPanoUrl(lat,lon){
    return 'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint='+encodeURIComponent(lat+','+lon);
  }
  function showStreet(name,lat,lon){
    var card=document.getElementById('streetCard'), img=document.getElementById('streetImg'), ttl=document.getElementById('streetTitle'), note=document.getElementById('streetNote');
    card.style.display='block';
    ttl.innerHTML='<strong>Street View:</strong> '+esc(name||'Station');
    note.textContent='';
    var pano=streetPanoUrl(lat,lon);
    note.innerHTML='<a style="color:#7fc8ff" target="_blank" rel="noopener" href="'+pano+'">Open Street View in Google Maps</a>';
    img.onerror=function(){ note.innerHTML='Street preview unavailable on this device/browser. <a style="color:#7fc8ff" target="_blank" rel="noopener" href="'+pano+'">Open Street View in Google Maps</a>'; };
    img.src=streetUrl(lat,lon,900,360);
  }
  function render(){
    var q=(document.getElementById('q').value||'').trim();
    var rowsEl=document.getElementById('rows'); rowsEl.innerHTML='';
    var cardsEl=document.getElementById('cards'); cardsEl.innerHTML='';
    var shown=0;
    all.forEach(function(r){
      if(!match(r,q)) return;
      shown++;
      var tr=document.createElement('tr');
      var lat0=esc(r.latitude||r.lat||''), lon0=esc(r.longitude||r.lon||'');
      var gdir=(lat0 && lon0) ? ('https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(lat0+','+lon0)+'&travelmode=driving') : '#';
      var stn=(r.unitid||r.name||r.unitname||'');
      var mapLink='/stations-map?station='+encodeURIComponent(String(stn));
      var arroLink=arroUrl(r);
      tr.innerHTML=''
        +'<td>'+r.index+'</td>'
        +'<td>'+esc(r.unitid||'')+'</td>'
        +'<td><input data-k="name" value="'+esc(r.name||r.unitname||'')+'" style="min-width:220px"></td>'
        +'<td><input class="num" data-k="enabled" value="'+esc(r.enabled||'')+'"></td>'
        +'<td><input class="num" data-k="lat" value="'+lat0+'"></td>'
        +'<td><input class="num" data-k="lon" value="'+lon0+'"></td>'
        +'<td><input class="num" data-k="elevation" value="'+esc(r.elevation||'')+'"></td>'
        +'<td>'+esc(r.sensor_types||'')+'</td>'
        +'<td>'+esc(r.sensor_ids||'')+'</td>'
        +'<td>'+esc(r.arro_site_id||'')+'</td>'
        +'<td>'+esc(r.device_ids||'')+'</td>'
        +'<td>'+esc(r.kml_name||'')+'</td>'
        +'<td>'+esc(r.source||'')+'</td>'
        +'<td><a href="'+mapLink+'" style="color:#7fc8ff">Map</a></td>'
        +'<td>'+(arroLink?('<a href="'+arroLink+'" target="_blank" rel="noopener" style="color:#7fc8ff">ARRO</a>'):'-')+'</td>'
        +'<td><input class="num" data-k="icon" value="'+esc(r.icon||'')+'"></td>'
        +'<td><input class="num" data-k="style" value="'+esc(r.style||'')+'"></td>'
        +'<td><input class="num" data-k="locked" value="'+esc(r.locked||'')+'"></td>'
        +'<td>'+(lat0&&lon0?('<a href="'+gdir+'" target="_blank" rel="noopener" style="color:#7fc8ff">Go</a>'):'-')+'</td>'
        +'<td>'+(lat0&&lon0?('<button class="street">View</button>'):'-')+'</td>'
        +'<td><button class="save">Save</button> <button class="del" style="margin-left:.3rem">Delete</button></td>';
      var streetBtn=tr.querySelector('.street');
      if(streetBtn){ streetBtn.addEventListener('click', function(){ showStreet(r.name||r.unitname||('Station '+r.index), lat0, lon0); }); }
      tr.querySelector('.save').addEventListener('click', function(){
        savePatch({
          index:r.index,
          name:tr.querySelector('input[data-k="name"]').value.trim(),
          enabled:tr.querySelector('input[data-k="enabled"]').value.trim(),
          lat:tr.querySelector('input[data-k="lat"]').value.trim(),
          lon:tr.querySelector('input[data-k="lon"]').value.trim(),
          elevation:tr.querySelector('input[data-k="elevation"]').value.trim(),
          icon:tr.querySelector('input[data-k="icon"]').value.trim(),
          style:tr.querySelector('input[data-k="style"]').value.trim(),
          locked:tr.querySelector('input[data-k="locked"]').value.trim()
        }, r.index);
      });
      var delBtn=tr.querySelector('.del');
      if(delBtn){ delBtn.addEventListener('click', function(){
        if(!confirm('Delete station '+(r.name||r.unitname||r.index)+'?')) return;
        fetch('/api/stations/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({index:r.index})})
          .then(function(x){ return x.json(); })
          .then(function(d){ document.getElementById('msg').textContent = d.ok ? ('deleted station #'+r.index) : ('delete failed: '+(d.error||'unknown')); if(d.ok) load(); })
          .catch(function(){ document.getElementById('msg').textContent='delete failed'; });
      }); }
      rowsEl.appendChild(tr);

      var card=document.createElement('details'); card.className='st-card';
      var cLat=esc(r.latitude||r.lat||''), cLon=esc(r.longitude||r.lon||'');
      var cDir=(cLat&&cLon)?('https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(cLat+','+cLon)+'&travelmode=driving'):'#';
      var cStn=(r.unitid||r.name||r.unitname||'');
      var cMap='/stations-map?station='+encodeURIComponent(String(cStn));
      var cArro=arroUrl(r);
      card.innerHTML=''
        +'<summary><strong>'+esc(r.name||r.unitname||('Station #'+r.index))+'</strong> <span class="muted">#'+r.index+' · ID '+esc(r.unitid||'-')+'</span></summary>'
        +'<div class="st-body">'
        +'<div style="margin-bottom:.45rem"><a href="'+cMap+'" style="color:#7fc8ff">Open on Map</a>'+(cArro?(' · <a href="'+cArro+'" target="_blank" rel="noopener" style="color:#7fc8ff">ARRO</a>'):'')+'</div>'
        +((cLat&&cLon)?('<div style="margin-bottom:.45rem"><a href="'+cDir+'" target="_blank" rel="noopener" style="color:#7fc8ff">Directions</a> · <a href="'+streetPanoUrl(cLat,cLon)+'" target="_blank" rel="noopener" style="color:#7fc8ff">Open Street</a> · <button class="street-inline" type="button">Preview</button></div><img class="street-inline-img" style="display:none;width:100%;max-height:180px;object-fit:cover;border:1px solid #2a3948;border-radius:6px"><div class="street-inline-note muted" style="display:none;margin-top:.25rem"></div>'):'')
        +'<div class="muted" style="margin-bottom:.4rem">Sensor types: '+esc(r.sensor_types||'')+'<br>Sensor IDs: '+esc(r.sensor_ids||'')+'<br>ARRO site_id: '+esc(r.arro_site_id||'')+' · device_ids: '+esc(r.device_ids||'')+'<br>KML Name: '+esc(r.kml_name||'')+' · Source: '+esc(r.source||'')+'</div>'
        +'<div class="grid">'
        +'<div><label>Name</label><input data-k="name" value="'+esc(r.name||r.unitname||'')+'"></div>'
        +'<div><label>Enabled</label><input data-k="enabled" value="'+esc(r.enabled||'')+'"></div>'
        +'<div><label>Lat</label><input data-k="lat" value="'+esc(r.latitude||r.lat||'')+'"></div>'
        +'<div><label>Lon</label><input data-k="lon" value="'+esc(r.longitude||r.lon||'')+'"></div>'
        +'<div><label>Elevation</label><input data-k="elevation" value="'+esc(r.elevation||'')+'"></div>'
        +'<div><label>Icon</label><input data-k="icon" value="'+esc(r.icon||'')+'"></div>'
        +'<div><label>Style</label><input data-k="style" value="'+esc(r.style||'')+'"></div>'
        +'<div><label>Locked</label><input data-k="locked" value="'+esc(r.locked||'')+'"></div>'
        +'</div><div style="margin-top:.5rem"><button class="save">Save</button> <button class="del" style="margin-left:.3rem">Delete</button></div>'
        +'</div>';
      var sbtn=card.querySelector('.street-inline');
      if(sbtn){ sbtn.addEventListener('click', function(){
        var im=card.querySelector('.street-inline-img');
        var note=card.querySelector('.street-inline-note');
        if(!im) return;
        if(note) note.style.display='none';
        im.style.display='block';
        im.onerror=function(){
          im.style.display='none';
          if(note){
            note.style.display='block';
            note.innerHTML='Inline Street preview unavailable on this device/browser. Use <a href="'+streetPanoUrl(cLat,cLon)+'" target="_blank" rel="noopener" style="color:#7fc8ff">Open Street</a>.';
          }
        };
        im.src=streetUrl(cLat,cLon,640,280);
      }); }
      card.querySelector('.save').addEventListener('click', function(){
        savePatch({
          index:r.index,
          name:card.querySelector('input[data-k="name"]').value.trim(),
          enabled:card.querySelector('input[data-k="enabled"]').value.trim(),
          lat:card.querySelector('input[data-k="lat"]').value.trim(),
          lon:card.querySelector('input[data-k="lon"]').value.trim(),
          elevation:card.querySelector('input[data-k="elevation"]').value.trim(),
          icon:card.querySelector('input[data-k="icon"]').value.trim(),
          style:card.querySelector('input[data-k="style"]').value.trim(),
          locked:card.querySelector('input[data-k="locked"]').value.trim()
        }, r.index);
      });
      var cdel=card.querySelector('.del');
      if(cdel){ cdel.addEventListener('click', function(){
        if(!confirm('Delete station '+(r.name||r.unitname||r.index)+'?')) return;
        fetch('/api/stations/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({index:r.index})})
          .then(function(x){ return x.json(); })
          .then(function(d){ document.getElementById('msg').textContent = d.ok ? ('deleted station #'+r.index) : ('delete failed: '+(d.error||'unknown')); if(d.ok) load(); })
          .catch(function(){ document.getElementById('msg').textContent='delete failed'; });
      }); }
      cardsEl.appendChild(card);
    });
    document.getElementById('shown').textContent=shown;
  }
  document.getElementById('q').addEventListener('input', render);
  document.getElementById('reload').addEventListener('click', load);
  document.getElementById('upload').addEventListener('click', function(){
    var f=document.getElementById('csvFile').files[0];
    if(!f){ document.getElementById('msg').textContent='select csv first'; return; }
    var fr=new FileReader();
    fr.onload=function(){
      fetch('/api/stations/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:f.name,csv_text:String(fr.result||'')})})
        .then(r=>r.json()).then(d=>{ document.getElementById('msg').textContent = d.ok ? ('uploaded '+(d.count||0)+' rows') : ('upload failed: '+(d.error||'unknown')); load(); })
        .catch(function(){ document.getElementById('msg').textContent='upload failed'; });
    };
    fr.readAsText(f);
  });
  load();
})();
</script>
</div></body></html>"""

STATIONS_MAP_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Stations Map</title>
<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'/>
<link rel='stylesheet' href='https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css'/>
<link rel='stylesheet' href='https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css'/>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.35rem}#map{height:72vh;border:1px solid #2a3948;border-radius:8px}.muted{color:#9fb0c3}.touch-note{font-size:.9em;color:#9fb0c3}@media(max-width:900px){input{min-height:40px;font-size:16px}#map{height:76vh}}</style>
<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script><script src='https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js'></script></head><body><div class='page'>
<h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z'/><path d='M9 4v14'/><path d='M15 6v14'/></svg></span><span>Stations Map</span></h2>
<div class='muted' style='margin:-.2rem 0 .55rem'>Geospatial operations view of stations with packet recency coloring and quick context popups. Use this page to see where activity is fresh, stale, or missing at a glance.</div>
__NAV__
<div class='card'>
  <input id='q' placeholder='Type to filter markers by name/id...' style='min-width:280px'>
  <label class='muted' style='margin-left:.6rem'><input id='clustersOn' type='checkbox' checked> clusters</label>
  <label class='muted' style='margin-left:.6rem'><input id='hideStale' type='checkbox'> hide stale (red)</label>
  <span class='muted'>Total: <span id='total'>0</span> · Visible: <span id='vis'>0</span></span>
  <label class='muted' style='margin-left:.6rem'>Fade hours <input id='fadeHours' type='number' min='0.25' step='0.25' value='3' style='width:70px'></label>
  <label class='muted' style='margin-left:.6rem'>Packet time
    <select id='pktTimeMode'>
      <option value='age' selected>Age</option>
      <option value='exact'>Exact</option>
    </select>
  </label>
  <div id='pktFlash' class='touch-note'>Waiting for packets...</div>
  <div class='touch-note'>Legend: <span style='display:inline-block;width:10px;height:10px;border-radius:50%;background:#2ecc71;vertical-align:middle'></span> Fresh  →  <span style='display:inline-block;width:10px;height:10px;border-radius:50%;background:#e94c3c;vertical-align:middle'></span> Stale (fade window applies)</div>
  <div class='touch-note'>Tap a cluster to zoom. Marker touch targets enlarged for mobile.</div>
</div>
<div class='card'><div id='map'></div></div>
<script>
(function(){
  var all=[], map=L.map('map',{tapTolerance:25});
  var pointMarkersByName={};
  var initialFitDone=false;
  var pointMarkersByBom={};
  var lastSeenByName={};
  var lastSeenByBom={};
  var lastPacketsByName={};
  var lastPacketsByBom={};
  var stationParam=(new URLSearchParams(window.location.search).get('station')||'').trim();
  var focusDone=false;
  function norm(s){ return String(s||'').trim().toLowerCase().replace(/\s+/g,' '); }
  function firstCsv(v){ return String(v||'').split(',').map(function(x){return x.trim();}).filter(Boolean)[0]||''; }
  function arroUrl(r){
    var siteId=String(r.arro_site_id||'').trim();
    var devId=firstCsv(r.device_ids||'');
    if(!siteId) return '';
    var u='https://contrail-bom.onerain.au/administration/sensor/details/?site_id='+encodeURIComponent(siteId);
    if(devId) u += '&device_id='+encodeURIComponent(devId);
    return u;
  }
  function fadeWindowMs(){
    var h=Number((document.getElementById('fadeHours')||{}).value||3);
    if(!isFinite(h)||h<=0) h=3;
    return h*3600*1000;
  }
  function mix(a,b,t){ return Math.round(a + (b-a)*Math.max(0,Math.min(1,t))); }
  function colorForAge(ageMs){
    var W=fadeWindowMs();
    var t=Math.max(0,Math.min(1, ageMs/W));
    // fresh=green, stale=red
    var r=mix(46, 233, t), g=mix(204, 76, t), bl=mix(113, 60, t);
    return 'rgb('+r+','+g+','+bl+')';
  }
  function recentTsForStationRef(ref){
    if(!ref) return null;
    var bom=String(ref.bom||'').trim();
    var nm=norm(ref.name||'');
    if(bom && lastSeenByBom[bom]) return lastSeenByBom[bom];
    if(nm && lastSeenByName[nm]) return lastSeenByName[nm];
    return null;
  }
  function pushRecentPacket(store, k, pkt){
    if(!k) return;
    var arr=store[k]||[];
    arr.unshift(pkt);
    if(arr.length>4) arr=arr.slice(0,4);
    store[k]=arr;
  }

  function stationIsStale(r){
    var now=Date.now();
    var bom=(r&&r.unitid!=null)?String(r.unitid).trim():'';
    var nm=norm(r.name||r.unitname||'');
    var ts=recentTsForStationRef({bom:bom,name:nm});
    if(!ts) return true;
    return (now-ts) >= fadeWindowMs();
  }
  function applyMarkerColorForStation(r,m){
    var now=Date.now();
    var bom=(r&&r.unitid!=null)?String(r.unitid).trim():'';
    var nm=norm(r.name||r.unitname||'');
    var ts=recentTsForStationRef({bom:bom,name:nm});
    var col = ts ? colorForAge(now-ts) : '#e94c3c';
    m.setStyle({color:col, fillColor:col, fillOpacity:0.9, weight:2});
  }
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);
  var clustered=(L.markerClusterGroup ? L.markerClusterGroup({
    chunkedLoading:true,
    showCoverageOnHover:false,
    spiderfyOnMaxZoom:true,
    disableClusteringAtZoom:13,
    maxClusterRadius:45,
    iconCreateFunction: function(cluster){
      var kids=cluster.getAllChildMarkers();
      var now=Date.now();
      var newestTs=null;
      for(var i=0;i<kids.length;i++){
        var ref=kids[i]._stationRef||null;
        var ts=recentTsForStationRef(ref);
        if(ts && (!newestTs || ts>newestTs)) newestTs=ts;
      }
      var col=newestTs ? colorForAge(now-newestTs) : '#e94c3c';
      var cnt=cluster.getChildCount();
      var html='<div style="background:'+col+';width:32px;height:32px;border-radius:16px;border:2px solid rgba(255,255,255,.35);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700">'+cnt+'</div>';
      return L.divIcon({html:html,className:'fw-cluster',iconSize:[32,32]});
    }
  }) : L.layerGroup());
  var plain=L.layerGroup();
  var useClusters=!!L.markerClusterGroup;
  map.addLayer(clustered);
  function match(r,q){ if(!q) return true; q=q.toLowerCase(); return [r.name,r.unitname,r.unitid].some(function(v){return String(v||'').toLowerCase().indexOf(q)>=0;}); }
  function ageText(ts){
    var t=Date.parse(ts||'');
    if(!isFinite(t)) return '';
    var sec=Math.max(0, Math.floor((Date.now()-t)/1000));
    if(sec<60) return sec+'s ago';
    var min=Math.floor(sec/60);
    if(min<60) return min+'m ago';
    var hr=Math.floor(min/60);
    if(hr<48) return hr+'h ago';
    var d=Math.floor(hr/24);
    return d+'d ago';
  }
  function markerHtml(r, lat, lon){
    var dir='https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(String(lat)+','+String(lon))+'&travelmode=driving';
    var sv='https://maps.googleapis.com/maps/api/streetview?size=360x180&location='+encodeURIComponent(String(lat)+','+String(lon))+'&fov=90&pitch=0&source=outdoor';
    var pano='https://www.google.com/maps/@?api=1&map_action=pano&viewpoint='+encodeURIComponent(String(lat)+','+String(lon));
    var bom=(r&&r.unitid!=null)?String(r.unitid).trim():'';
    var nm=norm(r.name||r.unitname||'');
    var lps=(bom && lastPacketsByBom[bom]) ? lastPacketsByBom[bom] : (lastPacketsByName[nm]||[]);
    var st=(r.unitid||r.name||r.unitname||'');
    var stLink='/stations?q='+encodeURIComponent(String(st));
    var arro=arroUrl(r);
    var name=String(r.name||r.unitname||'Station');
    var meta='';
    meta += '<div><b>BoM_Stn#:</b> '+String(r.unitid||'-')+'</div>';
    meta += '<div><b>Location:</b> '+lat+', '+lon+(r.elevation?(' · elev '+r.elevation+' m'):'')+'</div>';
    if(r.sensor_types) meta += '<div><b>Sensor types:</b> '+String(r.sensor_types)+'</div>';
    if(r.sensor_ids) meta += '<div><b>Sensor IDs:</b> '+String(r.sensor_ids)+'</div>';
    if(r.arro_site_id||r.device_ids) meta += '<div><b>ARRO:</b> site_id '+String(r.arro_site_id||'-')+' · device_ids '+String(r.device_ids||'-')+'</div>';
    if(r.kml_name||r.source) meta += '<div><b>Catalog:</b> '+String(r.kml_name||'-')+' · '+String(r.source||'-')+'</div>';

    var rowStyle='display:flex;justify-content:space-between;gap:.7rem;padding:.15rem 0;border-bottom:1px dashed rgba(180,210,240,.16)';
    function kv(k,v){ return '<div style="'+rowStyle+'"><span style="color:#9fc2e6">'+k+'</span><span style="color:#f4f8ff;font-weight:600">'+v+'</span></div>'; }
    var loc=lat+', '+lon;
    if(r.elevation) loc += ' · '+r.elevation+' m';
    var chips=''
      +'<a href="'+stLink+'" style="text-decoration:none;color:#dff3ff;background:#20486a;border:1px solid #3e6f97;padding:.24rem .52rem;border-radius:999px">Stations</a>'
      +(arro?(' <a href="'+arro+'" target="_blank" rel="noopener" style="text-decoration:none;color:#dff3ff;background:#20486a;border:1px solid #3e6f97;padding:.24rem .52rem;border-radius:999px">ARRO</a>'):'')
      +' <a href="'+dir+'" target="_blank" rel="noopener" style="text-decoration:none;color:#dff3ff;background:#20486a;border:1px solid #3e6f97;padding:.24rem .52rem;border-radius:999px">Directions</a>'
      +' <a href="'+pano+'" target="_blank" rel="noopener" style="text-decoration:none;color:#dff3ff;background:#20486a;border:1px solid #3e6f97;padding:.24rem .52rem;border-radius:999px">Street</a>';

    return ''
      +'<div style="min-width:270px;max-width:380px;line-height:1.45;color:#f4f8ff;font-size:14px;background:#122235;border:1px solid #2c4663;border-radius:8px;padding:.62rem .68rem">'
      +'<div style="font-weight:700;font-size:1.08em;margin-bottom:.48rem;color:#ffffff">'+name+'</div>'
      +kv('BoM_Stn#', String(r.unitid||'-'))
      +kv('Location', loc)
      +'<div style="margin:.55rem 0;padding:.55rem .6rem;background:#18324f;border:1px solid #2f5b84;border-radius:8px;color:#ffffff">'
      +'<div style="font-weight:700;margin-bottom:.35rem">Recent packets</div>'
      +(function(){
          if(!lps || !lps.length) return '<div style="color:#dcecff">No packet data yet</div>';
          var mode=((document.getElementById('pktTimeMode')||{}).value||'age');
          function ttxt(lp){
            if(mode==='exact'){
              var t=lp.ts?new Date(lp.ts):null;
              return (t && !isNaN(t.getTime())) ? t.toLocaleTimeString() : String(lp.ts||'-');
            }
            return String(ageText(lp.ts)||'-');
          }
          function btxt(lp){
            var raw='';
            if(lp.binary) raw=String(lp.binary).replace(/[^01]/g,'');
            if(!raw){
              var v=Number(lp.data_val);
              if(isFinite(v)){
                raw=(Math.trunc(v)>>>0).toString(2);
                raw=raw.padStart(Math.max(8,raw.length),'0');
              }
            }
            if(!raw) return 'n/a';
            var groups=[];
            for(var i=0;i<raw.length;i+=8) groups.push(raw.slice(i,i+8));
            return groups.join(' ');
          }
          var h='';
          lps.slice(0,4).forEach(function(lp){
            h+='<details style="border:1px solid rgba(190,220,255,.2);border-radius:6px;padding:.22rem .38rem;margin:.28rem 0;background:rgba(8,20,34,.35)">';
            h+='<summary style="cursor:pointer;list-style:none;display:flex;justify-content:space-between;gap:.6rem">'
              +'<span style="color:#ffffff">'+String(lp.sensor||'-')+'</span>'
              +'<span style="color:#ffffff">'+String(lp.data_val==null?'-':lp.data_val)+'</span>'
              +'<span style="color:#dcecff">'+ttxt(lp)+'</span>'
              +'</summary>';
            h+='<div style="padding:.26rem .1rem .18rem .1rem;color:#dcecff;font-family:monospace;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere">binary:\\n'+btxt(lp)+'</div>';
            h+='</details>';
          });
          return h;
        })()
      +'</div>'
      +'<div style="display:flex;flex-wrap:wrap;gap:.42rem .48rem;margin:.48rem 0 .55rem 0">'+chips+'</div>'
      +'<details style="margin:.2rem 0 .4rem 0">'
      +'<summary style="cursor:pointer;color:#9fc2e6">More details</summary>'
      +'<div style="margin-top:.45rem">'
      +(r.sensor_types?kv('Sensor types', String(r.sensor_types)):'')
      +(r.sensor_ids?kv('Sensor IDs', String(r.sensor_ids)):'')
      +((r.arro_site_id||r.device_ids)?kv('ARRO IDs', 'site '+String(r.arro_site_id||'-')+' · dev '+String(r.device_ids||'-')):'')
      +((r.kml_name||r.source)?kv('Catalog', String(r.kml_name||'-')+' · '+String(r.source||'-')):'')
      +'</div></details>'
      +'<details>'
      +'<summary style="cursor:pointer;color:#9fc2e6">Show Street View</summary>'
      +'<img src="'+sv+'" style="margin-top:.35rem;width:100%;max-width:340px;border:1px solid #2a3948;border-radius:6px" onerror="this.style.display=&quot;none&quot;">'
      +'</details>'
      +'</div>';
  }
  function render(){
    var q=(document.getElementById('q').value||'').trim();
    var hideStale=!!(document.getElementById('hideStale')&&document.getElementById('hideStale').checked);
    clustered.clearLayers();
    plain.clearLayers();
    pointMarkersByName={};
    pointMarkersByBom={};
    var pts=[];
    all.forEach(function(r){
      if(!match(r,q)) return;
      if(hideStale && stationIsStale(r)) return;
      if(r.latitude===''||r.longitude==='') return;
      var lat=Number(r.latitude), lon=Number(r.longitude);
      if(!isFinite(lat)||!isFinite(lon)) return;
      pts.push([lat,lon]);
      var m=L.circleMarker([lat,lon],{
        radius:8,
        weight:2,
        color:'#e94c3c',
        fillColor:'#e94c3c',
        fillOpacity:0.9
      });
      m.bindPopup(markerHtml(r,lat,lon));
      m.on('click', function(){ m.openPopup(); });
      m._stationRef={name:(r.name||r.unitname||''), bom:(r.unitid||'')};
      pointMarkersByName[norm(r.name||r.unitname||'')] = m;
      if(r.unitid!==undefined && r.unitid!==null && String(r.unitid).trim()!=='') pointMarkersByBom[String(r.unitid).trim()] = m;
      applyMarkerColorForStation(r,m);
      if(useClusters) clustered.addLayer(m); else plain.addLayer(m);
    });
    document.getElementById('vis').textContent=pts.length;
    if(pts.length && !initialFitDone){ map.fitBounds(L.latLngBounds(pts).pad(0.12)); initialFitDone=true; }
    if(stationParam && !focusDone){
      var q=String(stationParam).trim();
      var m=pointMarkersByBom[q] || pointMarkersByName[norm(q)] || null;
      if(m){
        focusDone=true;
        map.setView(m.getLatLng(), Math.max(map.getZoom(), 13));
        m.openPopup();
      }
    }
  }
  function seedRecentFromHistory(){
    fetch('/api/events?limit=1200').then(function(r){return r.json();}).then(function(d){
      var evs=d.events||[];
      for(var i=0;i<evs.length;i++){
        var ev=evs[i]||{};
        var sm=ev.sensor_map||null;
        var ts=Date.parse(ev.ts||'');
        if(!sm || !isFinite(ts)) continue;
        var bom=String(sm.site_id_bom||'').trim();
        var key=norm(sm.site||'');
        if(bom) lastSeenByBom[bom]=Math.max(lastSeenByBom[bom]||0, ts);
        if(key) lastSeenByName[key]=Math.max(lastSeenByName[key]||0, ts);

        var de=ev.decode||{}, fr=ev.frame||{};
        var pbin=String(fr.payload_bits||de.payload_bits||'').trim();
        if(pbin.length>96) pbin=pbin.slice(0,96)+'…';
        var pkt={
          ts: ev.ts||'',
          sensor: sm.sensor||'',
          data_val: (de.data_val!==undefined?de.data_val:null),
          binary: pbin
        };
        if(bom) pushRecentPacket(lastPacketsByBom, bom, pkt);
        if(key) pushRecentPacket(lastPacketsByName, key, pkt);
      }
      refreshAllMarkerColors();
      render();
    }).catch(function(){});
  }

  fetch('/api/stations/rows?limit=50000').then(function(r){return r.json();}).then(function(d){
    all=d.rows||[]; document.getElementById('total').textContent=all.length; render();
    seedRecentFromHistory();
    setTimeout(function(){ map.invalidateSize(); }, 120);
  }).catch(function(){ setTimeout(function(){ map.invalidateSize(); }, 120); });
  function updateFreshnessFromPacket(ev){
    var sm=(ev&&ev.sensor_map)||null;
    var pf=document.getElementById('pktFlash');
    if(!pf) return;
    if(sm){
      var now=Date.now();
      var bom=String(sm.site_id_bom||'').trim();
      var key=norm(sm.site||'');
      if(bom) lastSeenByBom[bom]=now;
      if(key) lastSeenByName[key]=now;
      var de=(ev&&ev.decode)||{}, fr=(ev&&ev.frame)||{};
      var pbin=String(fr.payload_bits||de.payload_bits||'').trim();
      if(pbin.length>96) pbin=pbin.slice(0,96)+'…';
      var pkt={ts: ev.ts||new Date(now).toISOString(), sensor: sm.sensor||'', data_val:(de.data_val!==undefined?de.data_val:null), binary:pbin};
      if(bom) pushRecentPacket(lastPacketsByBom, bom, pkt);
      if(key) pushRecentPacket(lastPacketsByName, key, pkt);

      var m=null;
      if(bom && pointMarkersByBom[bom]) m=pointMarkersByBom[bom];
      if(!m && key) m=pointMarkersByName[key] || null;
      if(m){
        var col=colorForAge(0);
        m.setStyle({color:col, fillColor:col, fillOpacity:0.95, weight:2.5});
        // Refresh popup body to include latest packet values/timestamp.
        var ref=m._stationRef||{};
        var rr={name:ref.name||sm.site||'', unitname:ref.name||sm.site||'', unitid:ref.bom||sm.site_id_bom||''};
        m.setPopupContent(markerHtml(rr, m.getLatLng().lat, m.getLatLng().lng));
        if(clustered && clustered.refreshClusters) try{ clustered.refreshClusters(); }catch(e){}
        pf.textContent='Packet mapped: '+(sm.site||('BoM# '+(sm.site_id_bom||'?')))+' ('+(sm.sensor||'')+')';
        pf.style.color='#5cd66f';
      } else {
        pf.textContent='Packet unmatched station on map: '+(sm.site||('BoM# '+(sm.site_id_bom||'?')));
        pf.style.color='#f36f6f';
      }
    } else {
      pf.textContent='Packet received with no station mapping';
      pf.style.color='#f36f6f';
    }
  }

  function refreshAllMarkerColors(){
    all.forEach(function(r){
      var m=null;
      var bom=(r&&r.unitid!=null)?String(r.unitid).trim():'';
      if(bom && pointMarkersByBom[bom]) m=pointMarkersByBom[bom];
      if(!m){
        var key=norm(r.name||r.unitname||'');
        m=pointMarkersByName[key]||null;
      }
      if(m) applyMarkerColorForStation(r,m);
    });
    if(clustered && clustered.refreshClusters) try{ clustered.refreshClusters(); }catch(e){}
  }

  document.getElementById('q').addEventListener('input', render);
  var fh=document.getElementById('fadeHours');
  if(fh) fh.addEventListener('input', function(){ render(); });
  var hs=document.getElementById('hideStale');
  if(hs) hs.addEventListener('change', render);
  document.getElementById('clustersOn').addEventListener('change', function(){
    useClusters=!!this.checked;
    if(useClusters){ if(map.hasLayer(plain)) map.removeLayer(plain); if(!map.hasLayer(clustered)) map.addLayer(clustered); }
    else { if(map.hasLayer(clustered)) map.removeLayer(clustered); if(!map.hasLayer(plain)) map.addLayer(plain); }
    render();
  });

  var es=new EventSource('/api/live');
  es.onmessage=function(m){
    try{ var ev=JSON.parse(m.data); updateFreshnessFromPacket(ev); }catch(e){}
  };
  setInterval(function(){
    var hs=document.getElementById('hideStale');
    if(hs && hs.checked) render(); else refreshAllMarkerColors();
  }, 30000);
})();
</script>
</div></body></html>"""

TRIP_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Trip Planning</title>
<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'/>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,button{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.35rem;box-sizing:border-box;max-width:100%;line-height:1.2}input{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.row{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}.grow{flex:1 1 280px}.muted{color:#9fb0c3}#map{height:52vh;border:1px solid #2a3948;border-radius:8px}.wp{padding:.45rem;border:1px solid #2a3948;border-radius:8px;margin:.4rem 0;background:#111a22}.wp b{display:block;margin-bottom:.2rem}.trip-entry{padding:.45rem .55rem}.trip-input,.trip-btn{height:32px;min-height:32px;max-height:32px;line-height:1;padding:.12rem .45rem;-webkit-appearance:none;appearance:none;font-size:16px}@media(max-width:900px){input,button{width:100%}.trip-entry{padding:.38rem .5rem}.trip-input,.trip-btn{height:32px !important;min-height:32px !important;max-height:32px !important;line-height:1 !important;font-size:16px !important;padding:.1rem .45rem !important}.row{flex-direction:column;align-items:stretch}.page{padding:.7rem}}</style>
<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script></head><body><div class='page'>
<h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 7h13'/><path d='M3 12h9'/><path d='M3 17h11'/><path d='M17 7l4 4-4 4'/></svg></span><span>Trip Planning</span></h2>
<div class='muted' style='margin:-.2rem 0 .55rem'>Route planning tool for field visits across stations and ad-hoc waypoints. Build, optimize, and hand off routes to Google Maps for navigation.</div>
__NAV__
<div class='card row trip-entry'>
  <input id='stationPick' list='stationsList' class='grow trip-input' placeholder='Add station waypoint (type to filter)'>
  <button id='addStation' class='trip-btn'>Add station</button>
  <datalist id='stationsList'></datalist>
</div>
<div class='card row trip-entry'>
  <input id='addr' class='grow trip-input' placeholder='Add waypoint by address'>
  <button id='addAddr' class='trip-btn'>Geocode & add</button>
</div>
<div class='card row trip-entry'>
  <input id='lat' class='trip-input' placeholder='Lat'>
  <input id='lon' class='trip-input' placeholder='Lon'>
  <input id='wpName' class='grow trip-input' placeholder='Name (optional)'>
  <button id='addLatLon' class='trip-btn'>Add lat/lon</button>
</div>
<div class='card'><div class='muted'>Tap map to add waypoint. Blue dots are known stations (tap to add).</div><div id='map'></div></div>
<div class='card'>
  <div class='row'>
    <strong>Waypoints</strong><span class='muted'>(<span id='count'>0</span>)</span>
    <label class='muted' style='margin-left:.5rem'><input id='optTime' type='checkbox' checked> optimize for travel time</label>
    <button id='buildRoute'>Build route</button>
    <button id='navGoogle'>Navigate in Google Maps</button>
    <button id='clear' style='margin-left:auto'>Clear</button>
  </div>
  <div id='routeInfo' class='muted' style='margin:.35rem 0'></div>
  <div id='wps'></div>
</div>
<script>
(function(){
  window.scrollTo(0,0);
  document.getElementById('map').setAttribute('tabindex','-1');
  var map=L.map('map',{tapTolerance:25, keyboard:false});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);
  map.setView([-27.47,153.03],8);
  var waypoints=[]; var markers=L.layerGroup().addTo(map); var stationLayer=L.layerGroup().addTo(map); var routeLayer=L.layerGroup().addTo(map); var stationsByName={};

  function esc(s){ return String(s||'').replace(/[&<>\"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
  function fmtDur(s){ s=Math.round(Number(s)||0); var h=Math.floor(s/3600), m=Math.round((s%3600)/60); return (h? (h+'h '):'')+m+'m'; }
  function fmtKm(m){ return ((Number(m)||0)/1000).toFixed(1)+' km'; }

  function render(){
    markers.clearLayers();
    var el=document.getElementById('wps'); el.innerHTML='';
    document.getElementById('count').textContent=waypoints.length;
    var pts=[];
    waypoints.forEach(function(w,i){
      pts.push([w.lat,w.lon]);
      var m=L.marker([w.lat,w.lon]).addTo(markers).bindPopup('<b>'+esc(w.name||('Waypoint '+(i+1)))+'</b><br>'+w.lat+', '+w.lon+'<br><a href="https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(w.lat+','+w.lon)+'&travelmode=driving" target="_blank" rel="noopener">Directions</a>');
      var d=document.createElement('div'); d.className='wp';
      d.innerHTML='<b>'+(i+1)+'. '+esc(w.name||('Waypoint '+(i+1)))+'</b><div class="muted">'+w.lat+', '+w.lon+' · '+esc(w.source||'manual')+'</div><div style="margin-top:.35rem"><button data-i="'+i+'">Remove</button> <a href="https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(w.lat+','+w.lon)+'&travelmode=driving" target="_blank" rel="noopener" style="color:#7fc8ff">Directions</a></div>';
      d.querySelector('button').addEventListener('click', function(){ waypoints.splice(i,1); render(); });
      el.appendChild(d);
    });
    if(pts.length){ map.fitBounds(L.latLngBounds(pts).pad(0.18)); }
    routeLayer.eachLayer(function(ly){ if(ly.bringToFront) ly.bringToFront(); });
  }

  function addWp(name, lat, lon, source){
    lat=Number(lat); lon=Number(lon);
    if(!isFinite(lat)||!isFinite(lon)) return;
    waypoints.push({name:name||'', lat:lat, lon:lon, source:source||'manual'});
    render();
  }

  function loadStations(){
    fetch('/api/stations/catalog?limit=50000').then(function(r){ return r.json(); }).then(function(d){
      var list=document.getElementById('stationsList'); list.innerHTML='';
      stationLayer.clearLayers();
      (d.stations||[]).forEach(function(s){
        if(!s||!s.name) return;
        stationsByName[s.name]=s;
        var o=document.createElement('option'); o.value=s.name; o.label=s.name+' ('+s.lat+', '+s.lon+')'; list.appendChild(o);
        var lat=Number(s.lat), lon=Number(s.lon);
        if(isFinite(lat)&&isFinite(lon)){
          var sm=L.circleMarker([lat,lon],{radius:5,color:'#7fc8ff',fillColor:'#2f8fd9',fillOpacity:0.75,weight:1.5});
          sm.bindPopup('<b>'+esc(s.name)+'</b><br>'+lat+', '+lon+'<br><button class="add-st" data-name="'+esc(s.name)+'" data-lat="'+lat+'" data-lon="'+lon+'">Add waypoint</button>');
          sm.on('popupopen', function(ev){
            var btn=ev.popup.getElement().querySelector('.add-st');
            if(btn){ btn.addEventListener('click', function(){
              var nm=btn.getAttribute('data-name')||'Station';
              var bl=Number(btn.getAttribute('data-lat')), bo=Number(btn.getAttribute('data-lon'));
              if(!isFinite(bl)||!isFinite(bo)) return;
              addWp(nm, bl, bo, 'station-map');
              map.closePopup();
            }); }
          });
          stationLayer.addLayer(sm);
        }
      });
    });
  }

  function googleNavUrl(points){
    if(!points || points.length<2) return '';
    var origin=points[0].lat+','+points[0].lon;
    var dest=points[points.length-1].lat+','+points[points.length-1].lon;
    var mid=points.slice(1,-1).map(function(p){ return p.lat+','+p.lon; }).join('|');
    var u='https://www.google.com/maps/dir/?api=1&travelmode=driving&origin='+encodeURIComponent(origin)+'&destination='+encodeURIComponent(dest);
    if(mid) u += '&waypoints='+encodeURIComponent(mid);
    return u;
  }

  function buildRoute(){
    if(waypoints.length<2){ document.getElementById('routeInfo').textContent='Need at least 2 waypoints'; return; }
    routeLayer.clearLayers();
    var optimize=!!document.getElementById('optTime').checked;
    var ordered=waypoints.slice();
    var coords=ordered.map(function(w){ return w.lon+','+w.lat; }).join(';');

    function drawFromCoords(arr, dist, dur){
      routeLayer.clearLayers();
      var latlngs=arr.map(function(c){ return [c[1],c[0]]; });
      if(!latlngs.length) return false;
      var line=L.polyline(latlngs,{color:'#ff2d55',weight:6,opacity:0.95}).addTo(routeLayer);
      if(line.bringToFront) line.bringToFront();
      document.getElementById('routeInfo').textContent='Route: '+fmtKm(dist)+' · '+fmtDur(dur)+(optimize?' · optimized':'');
      map.fitBounds(L.latLngBounds(latlngs).pad(0.12));
      return true;
    }

    function drawFallback(orderPoints, note){
      routeLayer.clearLayers();
      var latlngs=orderPoints.map(function(w){ return [Number(w.lat), Number(w.lon)]; }).filter(function(p){ return isFinite(p[0])&&isFinite(p[1]); });
      if(latlngs.length<2){ document.getElementById('routeInfo').textContent='Need at least 2 valid waypoints'; return; }
      var line=L.polyline(latlngs,{color:'#ff2d55',weight:5,opacity:0.85,dashArray:'8,6'}).addTo(routeLayer);
      if(line.bringToFront) line.bringToFront();
      map.fitBounds(L.latLngBounds(latlngs).pad(0.12));
      document.getElementById('routeInfo').textContent='Routing service unavailable; showing straight-line path'+(note?(' ('+note+')'):'');
    }

    var routeWithOrder=function(orderPoints){
      var c2=orderPoints.map(function(w){ return w.lon+','+w.lat; }).join(';');
      return fetch('https://router.project-osrm.org/route/v1/driving/'+c2+'?overview=full&geometries=geojson')
        .then(function(r){ if(!r.ok) throw new Error('http_'+r.status); return r.json(); })
        .then(function(d){
          if(!d || !d.routes || !d.routes.length) throw new Error('route_not_found');
          var rt=d.routes[0];
          var ok=drawFromCoords(rt.geometry.coordinates||[], rt.distance||0, rt.duration||0);
          if(!ok) throw new Error('empty_geometry');
          waypoints=orderPoints; render();
        });
    };

    if(optimize && waypoints.length>2){
      fetch('https://router.project-osrm.org/trip/v1/driving/'+coords+'?source=first&destination=last&roundtrip=false&overview=false')
        .then(function(r){ if(!r.ok) throw new Error('http_'+r.status); return r.json(); })
        .then(function(d){
          if(!d || !d.waypoints || !d.waypoints.length) throw new Error('optimize_failed');
          var ord=d.waypoints.map(function(w,idx){ return {w:w, idx:idx}; })
            .sort(function(a,b){ return (a.w.waypoint_index||0)-(b.w.waypoint_index||0); })
            .map(function(x){ return waypoints[x.idx]; })
            .filter(function(x){ return !!x; });
          return routeWithOrder(ord).catch(function(e){ drawFallback(ord, String(e&&e.message||'route failed')); });
        })
        .catch(function(e){ routeWithOrder(ordered).catch(function(e2){ drawFallback(ordered, String((e2&&e2.message)|| (e&&e.message) || 'failed')); }); });
    } else {
      routeWithOrder(ordered).catch(function(e){ drawFallback(ordered, String(e&&e.message||'failed')); });
    }
  }

  document.getElementById('addStation').addEventListener('click', function(){
    var sp=document.getElementById('stationPick');
    var n=(sp.value||'').trim();
    var s=stationsByName[n]; if(!s) return;
    addWp(n, s.lat, s.lon, 'station');
    sp.value='';
  });
  document.getElementById('addLatLon').addEventListener('click', function(){
    addWp((document.getElementById('wpName').value||'').trim(), document.getElementById('lat').value, document.getElementById('lon').value, 'latlon');
  });
  document.getElementById('addAddr').addEventListener('click', function(){
    var q=(document.getElementById('addr').value||'').trim(); if(!q) return;
    fetch('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q='+encodeURIComponent(q),{headers:{'Accept':'application/json'}})
      .then(function(r){return r.json();})
      .then(function(a){ if(!a||!a.length) return; addWp(q, a[0].lat, a[0].lon, 'address'); });
  });
  map.on('click', function(ev){ addWp('Map point', ev.latlng.lat, ev.latlng.lng, 'map'); });
  document.getElementById('buildRoute').addEventListener('click', buildRoute);
  document.getElementById('navGoogle').addEventListener('click', function(){
    var u=googleNavUrl(waypoints);
    if(!u){ document.getElementById('routeInfo').textContent='Need at least 2 waypoints for navigation'; return; }
    window.open(u, '_blank');
  });
  document.getElementById('clear').addEventListener('click', function(){ waypoints=[]; routeLayer.clearLayers(); document.getElementById('routeInfo').textContent=''; render(); });

  loadStations(); render();
})();
</script>
</div></body></html>"""

FILE_DROP_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB File Drop</title>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,button{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.35rem}.muted{color:#9fb0c3}.tbl{width:100%;border-collapse:collapse;margin-top:.45rem}.tbl th,.tbl td{border-bottom:1px solid #2a3948;padding:.35rem .4rem;text-align:left;vertical-align:top}.tbl th{color:#9fb0c3;font-weight:600;font-size:.9rem}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.right{text-align:right}@media(max-width:860px){.tbl{font-size:.92rem}.tbl th,.tbl td{padding:.42rem .35rem}}</style></head><body><div class='page'>
<h2 style='margin-top:0'>File Drop</h2>
<div class='muted' style='margin:-.2rem 0 .55rem'>Quick ingest page for CSV/text uploads used to update local metadata and mappings. Recent uploads below are timestamped so operators can confirm what was loaded and when.</div>
__NAV__
<div class='card'>
  <input id='f' type='file'> <button id='u'>Upload</button>
  <div id='m' class='muted' style='margin-top:.4rem'></div>
</div>
<div class='card'>
  <strong>Recent uploads</strong>
  <div id='mapStatus' class='muted' style='margin-top:.35rem'></div>
  <div id='lst' class='muted' style='margin-top:.4rem'>loading...</div>
</div>
<script>
(function(){
  function eh(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){ return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]); }); }
  function loadList(){
    fetch('/api/file_drop/list?limit=20').then(function(r){return r.json();}).then(function(d){
      var a=d.files||[];
      if(!a.length){ document.getElementById('lst').textContent='no uploads yet'; }
      else {
        var rows = a.map(function(x){
          var ts = String(x.mtime||'');
          var d = new Date(ts);
          var local = isNaN(d.getTime()) ? ts : d.toLocaleString();
          return '<tr>'
            +'<td class="mono">'+eh(local)+'</td>'
            +'<td class="mono">'+eh(ts)+'</td>'
            +'<td>'+eh(x.type||'generic')+'</td>'
            +'<td class="mono">'+eh(x.name||'')+'</td>'
            +'<td class="right mono">'+eh(String(x.size||0))+'</td>'
            +'</tr>';
        });
        document.getElementById('lst').innerHTML = ''
          +'<table class="tbl">'
          +'<thead><tr><th>Local time</th><th>UTC/ISO</th><th>Type</th><th>File</th><th class="right">Bytes</th></tr></thead>'
          +'<tbody>'+rows.join('')+'</tbody>'
          +'</table>';
      }
    }).catch(function(){ document.getElementById('lst').textContent='failed to load uploads'; });

    fetch('/api/sensor_map/status').then(function(r){return r.json();}).then(function(s){
      document.getElementById('mapStatus').textContent = s.exists ? ('Sensor map active: '+s.mapped_alert1_ids+' ALERT1 IDs ('+s.path+')') : 'Sensor map not loaded yet';
    }).catch(function(){ document.getElementById('mapStatus').textContent='sensor map status unavailable'; });
  }
  document.getElementById('u').addEventListener('click', function(){
    var f=document.getElementById('f').files[0]; if(!f){ document.getElementById('m').textContent='choose file first'; return; }
    var fr=new FileReader();
    fr.onload=function(){
      fetch('/api/file_drop/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:f.name, content:String(fr.result||'')})})
      .then(function(r){return r.json();}).then(function(d){
        var extra=(d.type==='sensor_map') ? (' mapped IDs='+String(d.mapped_alert1_ids||0)) : '';
        document.getElementById('m').textContent = d.ok ? ('uploaded: '+(d.path||'')+' ['+(d.type||'generic')+']'+extra) : ('upload failed: '+(d.error||'unknown'));
        loadList();
      })
      .catch(function(){ document.getElementById('m').textContent='upload failed'; });
    };
    fr.readAsText(f);
  });
  loadList();
})();
</script>
</div></body></html>"""

BITFLIPPER_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB BitFlipper</title>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea;position:relative}.page{padding:1rem;position:relative;z-index:1}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,button,select{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.35rem}.muted{color:#9fb0c3}.tbl{width:100%;border-collapse:collapse;margin-top:.45rem}.tbl th,.tbl td{border-bottom:1px solid #2a3948;padding:.35rem .4rem;text-align:left;vertical-align:top}.tbl th{color:#9fb0c3}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.yes{color:#6dd17c;font-weight:700}.no{color:#f36f6f;font-weight:700}a{color:#7fc8ff}.bf-bg{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);pointer-events:none;z-index:0}.bf-art{max-width:220px;max-height:220px;opacity:.16;filter:hue-rotate(75deg) saturate(2.4) brightness(.85)}.bf-art svg{display:block;margin:auto}.sugg-wrap{position:relative;display:inline-block}.sugg-list{position:absolute;left:0;top:100%;margin-top:4px;min-width:700px;max-width:min(1100px,90vw);max-height:320px;overflow:auto;background:#0f141a;border:1px solid #2a3948;border-radius:8px;z-index:30;box-shadow:0 8px 24px rgba(0,0,0,.35)}.sugg-item{padding:.42rem .55rem;white-space:normal;cursor:pointer;border-bottom:1px solid #1f2b37}.sugg-item:last-child{border-bottom:none}.sugg-item:hover{background:#172533}</style></head><body><div class='page'>
<h2 style='margin-top:0'>BitFlipper</h2>
<div class='muted' style='margin:-.2rem 0 .55rem'>Analyze likely ALERT address bit-flips and quickly pivot matching results to ARRO graph links. Upload a CSV in the known sensor export format and test one- or multi-bit flip scenarios.</div>
__NAV__
<div class='bf-bg' aria-hidden='true'>__BITFLIPPER_ART__</div>
<div class='card'>
  <label>Data source
    <select id='dataSource'>
      <option value='fwlab' selected>FW-LAB stations list (current catalog)</option>
      <option value='upload'>Upload CSV file</option>
    </select>
  </label><br><br>
  <label id='csvWrap'>CSV file <input type='file' id='csvFile' accept='.csv'></label><br><br>
  <label>Find station/site</label>
  <div class='sugg-wrap'>
    <input id='stationLookup' placeholder='Type BoM station # or site name' style='min-width:420px;width:min(900px,70vw)'>
    <div id='stationSuggestList' class='sugg-list' style='display:none'></div>
  </div>
  <button id='useSuggestion' type='button'>Use</button><br><br>
  <label>ALERT Address <input type='number' id='alertAddr' min='0'></label><br><br>
  <label>Bits to flip <input type='number' id='bitsToFlip' min='1' value='1'></label><br><br>
  <label>ARRO base URL <input id='arroBase' size='50' value='https://contrail-bom.onerain.au/graph/'></label><br><br>
  <button id='runBtn'>Run analysis</button>
</div>
<div class='card'><div id='output' class='muted'>Ready.</div></div>
<script>
(()=>{
  'use strict';
  function eh(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){ return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]); }); }
  const parseCSV = t => {
    const l=t.split(/\\r?\\n/).filter(x=>x.trim()); if(!l.length) return [];
    const h=l[0].split(',').map(x=>x.trim());
    return l.slice(1).map(r=>{ const c=r.split(','); const o={}; h.forEach((k,i)=>o[k]=(c[i]||'').trim()); return o; });
  };
  const rowsFromMetaCatalog = cat => {
    const stations=(cat&&cat.stations)||[];
    const sensors=(cat&&cat.sensors)||[];
    const byBom=new Map();
    stations.forEach(s=>{ const k=String(s.bom_stn||s.station_key||'').trim(); if(k) byBom.set(k,s); });
    return sensors.map(sn=>{
      const bom=String(sn.station_bom_stn||'').trim();
      const st=byBom.get(bom)||{};
      return {
        'Site': String(st.name||st.location||'').trim(),
        'Site ID': bom,
        'Sensor': String(sn.sensor_type||'').trim(),
        'Sensor ID': String(sn.sensor_id||sn.sensor_key||'').trim(),
        'site_id': String(sn.arro_site_id||st.arro_site_id||'').trim(),
        'device_id': String(sn.device_id||'').trim(),
      };
    }).filter(r=>r['Sensor ID']);
  };
  const alertFromSensorId = id => { const p=String(id||'').split('.'), l=p[p.length-1]; return /^\d+$/.test(l)?+l:null; };
  const combos=(a,k)=>{ const r=[];(function f(s,c){ if(c.length===k) return r.push(c.slice()); for(let i=s;i<a.length;i++) f(i+1,c.concat(a[i])); })(0,[]); return r; };
  const bin=n=>n.toString(2);
  const formatLocal=d=>{ const p=x=>String(x).padStart(2,'0'); return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };

  const dataSource=document.getElementById('dataSource');
  const csvWrap=document.getElementById('csvWrap');
  const csvFile=document.getElementById('csvFile');
  const stationLookup=document.getElementById('stationLookup');
  const stationSuggestList=document.getElementById('stationSuggestList');
  const useSuggestion=document.getElementById('useSuggestion');
  const alertAddrInput=document.getElementById('alertAddr');
  let hintRows=[];
  let hintMap=new Map();
  let selectedOriginLabel='';
  let selectedOriginSensorId='';

  function buildHints(rows){
    hintRows=(rows||[]).map(r=>Object.assign({},r));
    hintMap=new Map();
    const seen=new Set();
    hintRows.forEach(r=>{
      const site=String(r['Site']||'').trim();
      const siteId=String(r['Site ID']||'').trim();
      const sensor=String(r['Sensor']||'').trim();
      const sid=String(r['Sensor ID']||'').trim();
      const a=alertFromSensorId(sid);
      if(a==null) return;
      const label=(siteId||'n/a')+' · '+(site||'unknown')+' · '+(sensor||'sensor')+' · ALERT '+String(a);
      if(seen.has(label)) return;
      seen.add(label);
      hintMap.set(label, a);
    });
    renderSuggestions();
  }

  function renderSuggestions(){
    const q=String(stationLookup.value||'').trim().toLowerCase();
    const keys=[...hintMap.keys()];
    const list=q?keys.filter(k=>k.toLowerCase().includes(q)):keys;
    const top=list.slice(0,30);
    if(!top.length){ stationSuggestList.style.display='none'; stationSuggestList.innerHTML=''; return; }
    stationSuggestList.innerHTML=top.map(k=>'<div class="sugg-item" data-v="'+eh(k)+'">'+eh(k)+'</div>').join('');
    stationSuggestList.style.display='block';
  }

  function rowsFromUploadFile(){
    return new Promise((resolve,reject)=>{
      const f=csvFile.files[0];
      if(!f) return resolve([]);
      const rd=new FileReader();
      rd.onload=()=>resolve(parseCSV(String(rd.result||'')));
      rd.onerror=()=>reject(new Error('file_read_failed'));
      rd.readAsText(f);
    });
  }

  function loadRowsForSource(){
    if(dataSource.value==='fwlab'){
      return fetch('/api/meta/catalog').then(r=>r.json()).then(cat=>rowsFromMetaCatalog(cat));
    }
    return rowsFromUploadFile();
  }

  function applySuggestion(){
    const q=String(stationLookup.value||'').trim();
    if(!q) return;
    selectedOriginLabel='';
    selectedOriginSensorId='';
    let a = hintMap.get(q);
    let m = null;
    if(a!=null){
      selectedOriginLabel=q;
      m=hintRows.find(r=>{
        const site=String(r['Site']||'').trim();
        const siteId=String(r['Site ID']||'').trim();
        const sensor=String(r['Sensor']||'').trim();
        const sid=String(r['Sensor ID']||'').trim();
        const aa=alertFromSensorId(sid);
        const label=(siteId||'n/a')+' · '+(site||'unknown')+' · '+(sensor||'sensor')+' · ALERT '+String(aa==null?'':aa);
        return label===q;
      }) || null;
    }
    if(a==null){
      const ql=q.toLowerCase();
      m=hintRows.find(r=>{
        const site=String(r['Site']||'').toLowerCase();
        const siteId=String(r['Site ID']||'').toLowerCase();
        const sid=String(r['Sensor ID']||'').toLowerCase();
        const sensor=String(r['Sensor']||'').toLowerCase();
        return site.includes(ql)||siteId.includes(ql)||sid.includes(ql)||sensor.includes(ql);
      }) || null;
      if(m) a=alertFromSensorId(String(m['Sensor ID']||''));
    }
    if(m) selectedOriginSensorId=String(m['Sensor ID']||'').trim();
    if(a!=null) alertAddrInput.value=String(a);
  }

  useSuggestion.addEventListener('click', applySuggestion);
  stationLookup.addEventListener('input', renderSuggestions);
  stationLookup.addEventListener('focus', renderSuggestions);
  stationLookup.addEventListener('change', applySuggestion);
  stationLookup.addEventListener('keydown', (e)=>{ if(e.key==='Enter'){ e.preventDefault(); applySuggestion(); stationSuggestList.style.display='none'; } });
  stationSuggestList.addEventListener('click', (e)=>{
    const t=e.target.closest('.sugg-item'); if(!t) return;
    stationLookup.value=t.getAttribute('data-v')||'';
    applySuggestion();
    stationSuggestList.style.display='none';
  });
  document.addEventListener('click', (e)=>{ if(!e.target.closest('.sugg-wrap') && e.target!==useSuggestion) stationSuggestList.style.display='none'; });

  dataSource.onchange=()=>{
    csvWrap.style.display=(dataSource.value==='upload')?'':'none';
    loadRowsForSource().then(buildHints).catch(()=>buildHints([]));
  };
  csvFile.addEventListener('change', ()=>{ if(dataSource.value==='upload') loadRowsForSource().then(buildHints).catch(()=>buildHints([])); });
  dataSource.onchange();

  document.getElementById('runBtn').onclick=()=>{
    const alertAddr=document.getElementById('alertAddr');
    const bitsToFlip=document.getElementById('bitsToFlip');
    const arroBase=document.getElementById('arroBase');
    const out=document.getElementById('output');
    const f=csvFile.files[0];
    const addr=+alertAddr.value, n=+bitsToFlip.value;
    const base=arroBase.value||'https://contrail-bom.onerain.au/graph/';
    if(n<1||addr<0){ out.textContent='Invalid input.'; return; }

    const runWithRows=(rows)=>{
      if(!rows||!rows.length){ out.textContent='No rows found in selected data source.'; return; }
      rows = rows.map(r=>Object.assign({}, r));
      rows.forEach(r=>r._alert=alertFromSensorId(r['Sensor ID']||''));
      const bits=[...Array(bin(addr).length).keys()];
      const map=new Map();
      combos(bits,n).forEach(b=>{ let v=addr; b.forEach(x=>v^=1<<x); if(v!==addr){ if(!map.has(v)) map.set(v,[]); map.get(v).push(b);} });
      const results=[];
      map.forEach((bs,v)=>{ const m=rows.filter(r=>r._alert===v); bs.forEach(b=>{ if(m.length) m.forEach(x=>results.push({b,v,x})); else results.push({b,v,x:null}); }); });
      const originRows = rows.filter(r=>r._alert===addr);
      let originPreferred = null;
      if(selectedOriginSensorId){
        originPreferred = originRows.find(r=>String(r['Sensor ID']||'').trim()===selectedOriginSensorId) || null;
      }
      if(!originPreferred && selectedOriginLabel){
        originPreferred = originRows.find(r=>{
          const site=String(r['Site']||'').trim();
          const siteId=String(r['Site ID']||'').trim();
          const sensor=String(r['Sensor']||'').trim();
          const sid=String(r['Sensor ID']||'').trim();
          const aa=alertFromSensorId(sid);
          const label=(siteId||'n/a')+' · '+(site||'unknown')+' · '+(sensor||'sensor')+' · ALERT '+String(aa==null?'':aa);
          return label===selectedOriginLabel;
        }) || null;
      }
      if(!originPreferred && originRows.length) originPreferred = originRows[0];
      const originKey = originPreferred ? String((originPreferred.site_id||'')+'|'+(originPreferred.device_id||'')) : '';
      const sensors=[...new Set(results.filter(r=>r.x).map(r=>r.x.Sensor))].sort();
      out.innerHTML='';
      const top=document.createElement('div'); top.className='muted'; top.style.marginBottom='.4rem'; top.textContent='Found '+results.length+' candidate rows.'; out.appendChild(top);
      const filt=document.createElement('div');
      filt.innerHTML='<label>Filter by Sensor <select id="sensorFilter"><option value="">All sensors</option>'+sensors.map(s=>'<option>'+eh(s)+'</option>').join('')+'</select></label> <span id="arroFiltered" style="margin-left:.6rem"></span>';
      out.appendChild(filt);
      const wrap=document.createElement('div');
      wrap.innerHTML='<table class="tbl" id="flipTable"><thead><tr><th>Bits</th><th>Dec</th><th>Bin</th><th>Match</th><th>Site</th><th>Site ID</th><th>Sensor</th><th>Sensor ID</th></tr></thead><tbody>'+
        results.map(r=>'<tr data-sensor="'+eh(r.x?.Sensor||'')+'" data-site="'+eh(r.x?.site_id||'')+'" data-device="'+eh(r.x?.device_id||'')+'" data-match="'+(r.x?'1':'0')+'">'+
        '<td class="mono">'+eh(r.b.join(','))+'</td><td>'+eh(r.v)+'</td><td class="mono">'+eh(bin(r.v))+'</td><td class="'+(r.x?'yes':'no')+'">'+(r.x?'YES':'NO')+'</td><td>'+eh(r.x?.Site||'')+'</td><td>'+eh(r.x?.['Site ID']||'')+'</td><td>'+eh(r.x?.Sensor||'')+'</td><td>'+eh(r.x?.['Sensor ID']||'')+'</td></tr>').join('')+
        '</tbody></table>';
      out.appendChild(wrap);

      const updateArro=()=>{
        const now=new Date(), start=new Date(now-7*86400e3);
        const p=new URLSearchParams({refresh:'off',markers:'false',legend:'true',bin:'86400',time_zone:'Australia/Brisbane',invalid:'true',has_regular_sensors:'true',has_forecast_sensors:'false',for_forecast:'false',hidden_devices:'none',data_start:formatLocal(start),data_end:formatLocal(now)});
        const seen=new Set();
        // Always keep one baseline trace: the original selected sensor/source for this ALERT address.
        if(originKey && originKey!=='|'){ seen.add(originKey); p.append('devices[]',originKey); }
        // Add currently visible matched bit-flip candidates.
        document.querySelectorAll('#flipTable tbody tr').forEach(tr=>{ if(tr.style.display==='none'||tr.dataset.match!=='1') return; const k=tr.dataset.site+'|'+tr.dataset.device; if(!seen.has(k)){ seen.add(k); p.append('devices[]',k);} });
        const c=document.getElementById('arroFiltered'); c.innerHTML='';
        if(seen.size){ const a=document.createElement('a'); a.href=base+'?'+p.toString(); a.target='_blank'; a.rel='noopener'; a.textContent='Open ARRO graph ('+seen.size+' traces incl. original ALERT '+addr+')'; c.appendChild(a); }
      };
      document.getElementById('sensorFilter').onchange=(e)=>{ const v=e.target.value; document.querySelectorAll('#flipTable tbody tr').forEach(tr=>tr.style.display=(!v||tr.dataset.sensor===v)?'':'none'); updateArro(); };
      updateArro();
    };

    if(dataSource.value==='upload' && !f){ out.textContent='Choose a CSV file first, or switch data source to FW-LAB catalog.'; return; }
    out.textContent = (dataSource.value==='fwlab') ? 'Loading FW-LAB catalog…' : 'Loading CSV…';
    loadRowsForSource().then(runWithRows).catch(()=>{ out.textContent='Failed to load selected data source.'; });
  };
})();
</script>
</div></body></html>"""

OVERVIEW_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Overview</title>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem;border:1px solid #243243}a{color:#7fc8ff}.muted{color:#9fb0c3}h3{margin:.15rem 0 .4rem}.grid{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:.6rem}@media(max-width:860px){.grid{grid-template-columns:1fr}}</style></head><body><div class='page'>
<h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='9'/><path d='M8 9h8'/><path d='M8 12h8'/><path d='M8 15h5'/></svg></span><span>Overview</span></h2>
<div class='muted' style='margin:-.2rem 0 .55rem'>Quick orientation page for new operators. Each section below explains what the matching page is for and when to use it.</div>
__NAV__
<div class='grid'>
  <div class='card'><h3><a href='/'>Dashboard</a></h3><div class='muted'>Live status and packet activity overview for fast situational awareness.</div></div>
  <div class='card'><h3><a href='/packets'>Packets</a></h3><div class='muted'>Event stream table for recent decodes and detailed packet drill-down.</div></div>
  <div class='card'><h3><a href='/radio'>Radio</a></h3><div class='muted'>Waveform/waterfall monitoring for RF tuning and reception troubleshooting.</div></div>
  <div class='card'><h3><a href='/data'>Data</a></h3><div class='muted'>Time-series trends for sensor values with local/archive source control.</div></div>
  <div class='card'><h3><a href='/path'>Path</a></h3><div class='muted'>Terrain and Fresnel link analysis for path planning and comparisons.</div></div>
  <div class='card'><h3><a href='/stations'>Stations</a></h3><div class='muted'>Editable registry of station/site metadata used throughout the platform.</div></div>
  <div class='card'><h3><a href='/stations-map'>Stations Map</a></h3><div class='muted'>Map view of station locations and packet recency state.</div></div>
  <div class='card'><h3><a href='/trip'>Trip Planning</a></h3><div class='muted'>Build and optimize field routes, then hand off to navigation tools.</div></div>
  <div class='card'><h3><a href='/file_drop'>File Drop</a></h3><div class='muted'>Upload CSV/text files for metadata and mapping ingestion workflows.</div></div>
  <div class='card'><h3><a href='/bitflipper'>BitFlipper</a></h3><div class='muted'>Bit-flip analysis utility to find likely ALERT address collisions and open ARRO graphs.</div></div>
  <div class='card'><h3><a href='/forensics'>Forensics</a></h3><div class='muted'>Analyze anomalies, acceptance metrics, and decode error behavior.</div></div>
  <div class='card'><h3><a href='/admin'>Admin</a></h3><div class='muted'>Controlled operational changes and audited admin actions.</div></div>
  <div class='card'><h3><a href='/about'>About</a></h3><div class='muted'>Project documentation mirror from README and reference links.</div></div>
</div>
</div></body></html>"""

HELP_HTML = OVERVIEW_HTML.replace('<span>Overview</span>', '<span>Help</span>').replace('Quick orientation page for new operators.', 'Operator help and orientation page.').replace('<title>FW-LAB Overview</title>', '<title>FW-LAB Help</title>')

ADMIN_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Admin</title>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,button,select{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}a{color:#7fc8ff}.row{margin:.35rem 0}.grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:.6rem}.good{color:#6dd17c}.warn{color:#f2c14e}.bad{color:#f36f6f}pre{white-space:pre-wrap;max-height:220px;overflow:auto;background:#0f141a;border:1px solid #2a3948;padding:.55rem;border-radius:6px}@media(max-width:860px){.grid{grid-template-columns:1fr}input,button,select{min-height:40px;font-size:16px}}</style></head>
<body><div class='page'>
<h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='3'/><path d='M19.4 15a1 1 0 0 0 .2 1.1l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9V20a2 2 0 0 1-4 0v-.2a1 1 0 0 0-.6-.9 1 1 0 0 0-1.1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6H4a2 2 0 0 1 0-4h.2a1 1 0 0 0 .9-.6 1 1 0 0 0-.2-1.1l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1 1 0 0 0 1.1.2h0a1 1 0 0 0 .6-.9V4a2 2 0 0 1 4 0v.2a1 1 0 0 0 .6.9h0a1 1 0 0 0 1.1-.2l.1-.1a2 2 0 0 1 2.8 2.8l-.1.1a1 1 0 0 0-.2 1.1v0a1 1 0 0 0 .9.6H20a2 2 0 0 1 0 4h-.2a1 1 0 0 0-.9.6z'/></svg></span><span>Admin</span></h2>
<div class='muted' style='margin:-.2rem 0 .55rem'>Operational control page for receiver lifecycle, storage policy, and audited admin actions. Use this area for controlled changes and diagnostics snapshots.</div>
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

<div class='card'>
  <h3 style='margin:.1rem 0 .6rem'>Metadata history</h3>
  <div class='row'>
    <label>Entity <select id='metaEntity'><option value=''>all</option><option value='station'>station</option><option value='sensor'>sensor</option></select></label>
    <label style='margin-left:.6rem'>Operation <select id='metaOp'><option value=''>all</option><option value='upsert'>upsert</option><option value='delete'>delete</option></select></label>
    <button id='metaRefresh' style='margin-left:.6rem'>Refresh</button>
    <button id='metaCopy' style='margin-left:.4rem'>Copy JSON</button>
    <button id='metaDownload' style='margin-left:.4rem'>Download JSON</button>
  </div>
  <pre id='metaHist'>loading...</pre>
</div>
<script>
(function(){
  function g(o,k,d){ return (o && o[k]!==undefined && o[k]!==null) ? o[k] : d; }
  function setv(id,v){ document.getElementById(id).value = (v==null?'':v); }
  function num(id){ var x=parseFloat(document.getElementById(id).value); return isNaN(x)?null:x; }
  var lastPolicy=null, lastReceiver=null, lastStorage=null, lastAudit=[], lastMetaHistory=[];

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
  function loadMetaHistory(){
    fetch('/api/admin/meta/history?limit=100').then(function(r){return r.json();}).then(function(d){
      var rows=g(d,'events',[])||[];
      var ent=(document.getElementById('metaEntity').value||'').trim();
      var op=(document.getElementById('metaOp').value||'').trim();
      if(ent){ rows = rows.filter(function(e){ return String(g(g(e,'details',{}),'entity',''))===ent; }); }
      if(op){ rows = rows.filter(function(e){ return String(g(g(e,'details',{}),'op',''))===op || String(g(e,'action',''))===op; }); }
      lastMetaHistory = rows;
      document.getElementById('metaHist').textContent = rows.map(function(e){
        var det=g(e,'details',{});
        var snap=g(det,'snapshot','');
        var key=(g(det,'station_key','')||g(det,'sensor_key',''));
        return (g(e,'ts',''))+'  '+(g(e,'action',''))+'  '+(g(det,'entity',''))+'  '+(g(det,'op',''))+'  '+key+(snap?('  '+snap):'');
      }).join('\\n') || 'no metadata history yet';
    }).catch(function(){ document.getElementById('metaHist').textContent='failed to load metadata history'; });
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

  document.getElementById('metaRefresh').addEventListener('click', loadMetaHistory);
  document.getElementById('metaEntity').addEventListener('change', loadMetaHistory);
  document.getElementById('metaOp').addEventListener('change', loadMetaHistory);
  document.getElementById('metaCopy').addEventListener('click', function(){
    var txt = JSON.stringify(lastMetaHistory || [], null, 2);
    navigator.clipboard.writeText(txt).then(function(){
      document.getElementById('msg').textContent=' metadata history copied';
    }).catch(function(){
      document.getElementById('msg').textContent=' metadata copy failed';
    });
  });
  document.getElementById('metaDownload').addEventListener('click', function(){
    try {
      var txt = JSON.stringify(lastMetaHistory || [], null, 2);
      var blob = new Blob([txt], {type:'application/json'});
      var u = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = u;
      a.download = 'meta_history_'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function(){ URL.revokeObjectURL(u); }, 5000);
      document.getElementById('msg').textContent=' metadata history downloaded';
    } catch(_) {
      document.getElementById('msg').textContent=' metadata download failed';
    }
  });

  document.getElementById('copyDiag').addEventListener('click', function(){
    var snap = {
      ts: new Date().toISOString(),
      receiver: lastReceiver || {},
      storage: lastStorage || {},
      policy: lastPolicy || {},
      audit_recent: lastAudit || [],
      meta_history_recent: lastMetaHistory || []
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
  loadMetaHistory(); setInterval(loadMetaHistory,15000);
})();
</script></div></body></html>"""

TRENDS_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'><title>FW-LAB Data</title>
<script src='https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'></script>
<style>body{font-family:Arial;margin:0;background:#10151c;color:#d7e0ea}.page{padding:1rem}.card{background:#17212b;padding:.8rem;border-radius:8px;margin-bottom:.8rem}input,select,button{background:#0f141a;color:#d7e0ea;border:1px solid #2a3948;border-radius:4px;padding:.3rem}a{color:#7fc8ff}#chart{height:420px}.controls{display:flex;flex-wrap:wrap;gap:.35rem .5rem;align-items:center}@media(max-width:860px){.controls{display:grid;grid-template-columns:1fr 1fr;gap:.45rem}#chart{height:320px}input,select,button{min-height:40px;font-size:16px}}</style></head>
<body><div class='page'>
<h2 style='margin-top:0;display:flex;align-items:center;gap:.45rem'><span class='fw-ico'><svg viewBox='0 0 24 24' width='20' height='20' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M4 19h16'/><path d='m6 15 4-4 3 2 5-6'/><path d='m18 7 0 3h-3'/></svg></span><span>Data</span></h2>
<div class='muted' style='margin:-.2rem 0 .55rem'>Time-series trends view for sensor values with source selection (local/archive), windowing, and derived metrics. Use this page to inspect behavior over time and save repeat views.</div>
__NAV__<br><br>
<div class='card controls'>
Sensor ID: <input id='sensor' list='sensorList' style='width:120px' placeholder='e.g. 4099'>
<datalist id='sensorList'></datalist>
<button id='refreshSensors'>Sensors</button>
Window: <select id='window'><option value='15m'>15m</option><option value='1h'>1h</option><option value='6h'>6h</option><option value='24h' selected>24h</option></select>
Source: <select id='sourceMode'><option value='auto' selected>auto</option><option value='combined'>combined</option><option value='local'>local</option><option value='archive'>archive</option></select>
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
<div class='card'>
  <div class='muted small'>Coverage (hot vs cold)</div>
  <div style='height:10px;background:#0f141a;border:1px solid #2a3948;border-radius:6px;overflow:hidden;margin:.3rem 0'>
    <div id='covLocal' style='height:100%;width:0%;background:#5fa8ff;float:left'></div>
    <div id='covArchive' style='height:100%;width:0%;background:#5bbf7a;float:left'></div>
  </div>
  <div class='small'>hot/local: <span id='covLocalCount'>0</span> · cold/archive: <span id='covArchiveCount'>0</span></div>
</div>
<div class='card'><div id='chart'></div></div>
<script>
(function(){
  var sensor=document.getElementById('sensor'), win=document.getElementById('window'), sourceMode=document.getElementById('sourceMode'), metricMode=document.getElementById('metricMode'), threshold=document.getElementById('threshold'), timeMode=document.getElementById('timeMode'), msg=document.getElementById('msg');
  var sensorList=document.getElementById('sensorList'), refreshSensors=document.getElementById('refreshSensors');
  var viewName=document.getElementById('viewName'), saveView=document.getElementById('saveView'), savedViews=document.getElementById('savedViews');
  var ymin=document.getElementById('ymin'), ymax=document.getElementById('ymax');
  var latest=document.getElementById('latest'), minv=document.getElementById('min'), maxv=document.getElementById('max'), avgv=document.getElementById('avg');
  var covLocal=document.getElementById('covLocal'), covArchive=document.getElementById('covArchive');
  var covLocalCount=document.getElementById('covLocalCount'), covArchiveCount=document.getElementById('covArchiveCount');
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
      var lc=(d.stats && d.stats.local_count!=null)?Number(d.stats.local_count):0;
      var ac=(d.stats && d.stats.archive_count!=null)?Number(d.stats.archive_count):0;
      var tot=Math.max(1,lc+ac);
      if(covLocal) covLocal.style.width=(100*lc/tot).toFixed(1)+'%';
      if(covArchive) covArchive.style.width=(100*ac/tot).toFixed(1)+'%';
      if(covLocalCount) covLocalCount.textContent=String(lc);
      if(covArchiveCount) covArchiveCount.textContent=String(ac);
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
  if(qpSource && ['auto','combined','local','archive'].indexOf(qpSource) >= 0){ sourceMode.value = qpSource; }
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
  <div class='muted' style='margin:-.2rem 0 .55rem'>Real-time RF monitor with waveform/waterfall views and stream controls for signal quality checks. Use this page during live tuning and reception troubleshooting.</div>
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
<div class='muted' style='margin:-.2rem 0 .55rem'>Deep diagnostics for decode quality, anomaly patterns, and error distributions across chosen windows. Use this page to validate demod changes and investigate packet integrity issues.</div>
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
<div class='card'><strong>Fixed-pair pattern stats (recent sample)</strong><pre id='pairStats'>loading...</pre></div>
<div class='card'><strong>AFSK parity acceptance tracker (anomaly stats)</strong><pre id='anomStats'>loading...</pre></div>
<div class='card'><strong>Demod/Decode error statistics</strong>
  <div style='margin:.4rem 0'>
    <label class='muted'>Counting mode
      <select id='errMode' style='margin-left:.35rem'>
        <option value='occurrence'>Error occurrences</option>
        <option value='primary_packet'>Primary error per packet</option>
      </select>
    </label>
    <span id='errModeNote' class='muted' style='margin-left:.6rem'></span>
  </div>
  <div id='errStats'>loading...</div><div id='errDesc' class='muted' style='margin-top:.6rem'>loading...</div></div>
<div class='card'><button id='exportBundle'>Export SME bundle (.json)</button> <span id='exportMsg' class='muted'></span></div>
<script>
(function(){
  function g(o,k,d){ return (o&&o[k]!==undefined&&o[k]!==null)?o[k]:d; }
  var exportBtn=document.getElementById('exportBundle'), exportMsg=document.getElementById('exportMsg');
  var pairStats=document.getElementById('pairStats');
  var anomStats=document.getElementById('anomStats');
  var errStats=document.getElementById('errStats');
  var errDesc=document.getElementById('errDesc');

  fetch('/api/pair_pattern_stats?limit=4000').then(function(r){return r.json();}).then(function(d){
    function fmtRow(r){ return JSON.stringify(r.pattern)+'  -> '+r.count; }
    var lines=[];
    lines.push('strict-good top:');
    (d.strict_top||[]).slice(0,6).forEach(function(r){ lines.push('  '+fmtRow(r)); });
    lines.push('');
    lines.push('good-ish top:');
    (d.goodish_top||[]).slice(0,6).forEach(function(r){ lines.push('  '+fmtRow(r)); });
    lines.push('');
    lines.push('overall top:');
    (d.overall_top||[]).slice(0,6).forEach(function(r){ lines.push('  '+fmtRow(r)); });
    if(pairStats) pairStats.textContent = lines.join('\\n');
  }).catch(function(){ if(pairStats) pairStats.textContent='failed to load pattern stats'; });

  fetch('/api/anomaly_stats?limit=4000').then(function(r){return r.json();}).then(function(d){
    var c=d.counts||{}, p=d.pct||{};
    var out=[];
    out.push('decoded frames: '+(d.decoded_frames||0));
    out.push('');
    out.push('sensor_id=0      : '+(c.sensor_id_0||0)+' ('+(p.sensor_id_0||0)+'%)');
    out.push('data_val=0       : '+(c.data_val_0||0)+' ('+(p.data_val_0||0)+'%)');
    out.push('sensor_id=8191   : '+(c.sensor_id_8191||0)+' ('+(p.sensor_id_8191||0)+'%)');
    out.push('data_val=2047    : '+(c.data_val_2047||0)+' ('+(p.data_val_2047||0)+'%)  [display 002047]');
    out.push('tuple 8191/2047  : '+(c.tuple_8191_2047||0)+' ('+(p.tuple_8191_2047||0)+'%)');
    out.push('');
    out.push('acceptance target: all above percentages should trend down in A/B trials');
    if(anomStats) anomStats.textContent = out.join('\\n');
  }).catch(function(){ if(anomStats) anomStats.textContent='failed to load anomaly stats'; });

  function loadErrorStats(){
    var mode=(document.getElementById('errMode')||{}).value||'occurrence';
    fetch('/api/error_stats?limit=60000&mode='+encodeURIComponent(mode)).then(function(r){return r.json();}).then(function(d){
      var rows=d.rows||[];
      var totals=d.totals||{};
      var pktTotals=d.packet_totals||{};
      var pktErr=d.packet_with_errors||{};
      var modeNote=document.getElementById('errModeNote');
      if(modeNote) modeNote.textContent=d.counting_note||'';
      function fmtPct(v){ return (Number(v||0).toFixed(2))+'%'; }
      if(errStats){
        if(!rows.length){ errStats.textContent='no errors in sampled window'; }
        else {
          var html='<table style="width:100%;border-collapse:collapse"><thead><tr>'
            +'<th style="text-align:left;border-bottom:1px solid #2a3948;padding:.35rem">Error type</th>'
            +'<th style="text-align:right;border-bottom:1px solid #2a3948;padding:.35rem">30m %</th>'
            +'<th style="text-align:right;border-bottom:1px solid #2a3948;padding:.35rem">3h %</th>'
            +'<th style="text-align:right;border-bottom:1px solid #2a3948;padding:.35rem">24h %</th>'
            +'</tr></thead><tbody>';
          html+='<tr style="background:#111925">'
            +'<td style="padding:.35rem;border-bottom:1px solid #243243;font-weight:600">Total errors (100%)</td>'
            +'<td style="padding:.35rem;text-align:right;border-bottom:1px solid #243243">'+(totals.count_30m||0)+'</td>'
            +'<td style="padding:.35rem;text-align:right;border-bottom:1px solid #243243">'+(totals.count_3h||0)+'</td>'
            +'<td style="padding:.35rem;text-align:right;border-bottom:1px solid #243243">'+(totals.count_24h||0)+'</td>'
            +'</tr>';
          html+='<tr style="background:#0f1722">'
            +'<td style="padding:.35rem;border-bottom:1px solid #243243;font-weight:600">Packets in window</td>'
            +'<td style="padding:.35rem;text-align:right;border-bottom:1px solid #243243">'+(pktTotals['30m']||0)+'</td>'
            +'<td style="padding:.35rem;text-align:right;border-bottom:1px solid #243243">'+(pktTotals['3h']||0)+'</td>'
            +'<td style="padding:.35rem;text-align:right;border-bottom:1px solid #243243">'+(pktTotals['24h']||0)+'</td>'
            +'</tr>';
          html+='<tr style="background:#0f1722">'
            +'<td style="padding:.35rem;border-bottom:1px solid #243243;font-weight:600">Packets with any error</td>'
            +'<td style="padding:.35rem;text-align:right;border-bottom:1px solid #243243">'+(pktErr['30m']||0)+'</td>'
            +'<td style="padding:.35rem;text-align:right;border-bottom:1px solid #243243">'+(pktErr['3h']||0)+'</td>'
            +'<td style="padding:.35rem;text-align:right;border-bottom:1px solid #243243">'+(pktErr['24h']||0)+'</td>'
            +'</tr>';
          rows.forEach(function(rw){
            html+='<tr><td style="padding:.3rem;border-bottom:1px solid #243243">'+rw.code+'</td>'
                +'<td style="padding:.3rem;text-align:right;border-bottom:1px solid #243243">'+fmtPct(rw.pct_30m)+'</td>'
                +'<td style="padding:.3rem;text-align:right;border-bottom:1px solid #243243">'+fmtPct(rw.pct_3h)+'</td>'
                +'<td style="padding:.3rem;text-align:right;border-bottom:1px solid #243243">'+fmtPct(rw.pct_24h)+'</td></tr>';
          });
          html+='</tbody></table>';
          errStats.innerHTML=html;
        }
      }
      if(errDesc){
        if(!rows.length){
          errDesc.textContent='no error descriptions to show';
        } else {
          var html='<div style="font-weight:600;margin-bottom:.35rem">Error descriptions</div>';
          rows.forEach(function(rw, idx){
            html+='<div style="border:1px solid #2b3c50;background:#111925;border-radius:6px;padding:.55rem .6rem">';
            html+='<div style="font-family:monospace;color:#c6d4e3;background:#0d1622;border:1px solid #2a3a4e;padding:.32rem .45rem;border-radius:4px;display:inline-block">'+rw.code+'</div>';
            html+='<div style="color:#d7e0ea;line-height:1.42;margin-top:.42rem">'+(rw.description||'')+'</div>';
            html+='</div>';
            if(idx < rows.length-1) html+='<div style="height:.85rem"></div>';
          });
          errDesc.innerHTML=html;
        }
      }
    }).catch(function(){ if(errStats) errStats.textContent='failed to load error stats'; if(errDesc) errDesc.textContent='failed to load descriptions'; });
  }
  var em=document.getElementById('errMode');
  if(em) em.addEventListener('change', loadErrorStats);
  loadErrorStats();

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


def _pair_pattern_stats(store: 'EventStore', limit: int = 2000):
    limit = max(100, min(int(limit), 20000))
    try:
        store.poll_new()
        evs = list(store.events)[-limit:]
    except Exception:
        evs = []

    def observed_pair(ev):
        pb = str((ev.get('frame') or {}).get('payload_bits') or '')
        if len(pb) < 32:
            return None
        out = []
        for i in range(4):
            b = pb[i * 8:(i + 1) * 8]
            if len(b) != 8 or any(ch not in '01' for ch in b):
                return None
            out.append([int(b[6]), int(b[7])])
        return out

    def has_framing_bad(ev):
        codes = [str((e or {}).get('code', '')) for e in (ev.get('errors') or [])]
        for c in codes:
            if c.startswith('timing.hunt_timeout') or c.startswith('framing.word_start_stop_mismatch') or c.startswith('framing.length_mismatch'):
                return True
        return False

    import collections
    overall = collections.Counter()
    goodish = collections.Counter()
    strict = collections.Counter()

    for ev in evs:
        p = observed_pair(ev)
        if p is None:
            continue
        k = json.dumps(p)
        overall[k] += 1

        de = ev.get('decode') or {}
        q = ev.get('quality') or {}
        score = q.get('score', 0)
        st = ev.get('status', '')
        sid = de.get('sensor_id', 0)
        errs = ev.get('errors') or []

        if st in ('ok', 'warn') and isinstance(score, (int, float)) and score >= 0.70 and sid not in (None, 0) and not has_framing_bad(ev):
            goodish[k] += 1
        if st == 'ok' and isinstance(score, (int, float)) and score >= 0.85 and not errs:
            strict[k] += 1

    def top_rows(counter, n=10):
        out = []
        for k, c in counter.most_common(n):
            out.append({'pattern': json.loads(k), 'count': int(c)})
        return out

    return {
        'schema': 'fwlab.pair_pattern_stats.v1',
        'ts': datetime.utcnow().isoformat() + 'Z',
        'sample_limit': limit,
        'overall_top': top_rows(overall, 12),
        'goodish_top': top_rows(goodish, 12),
        'strict_top': top_rows(strict, 12),
    }


def _with_sensor_mapping(events):
    sm = _load_sensor_map()
    if not sm:
        return events
    out = []
    for ev in (events or []):
        try:
            e = dict(ev)
            de = dict((e.get('decode') or {}))
            sid = str(de.get('sensor_id', '')).strip()
            if sid and sid in sm:
                e['sensor_map'] = sm[sid]
            e['decode'] = de
            out.append(e)
        except Exception:
            out.append(ev)
    return out


def _error_stats(store: 'EventStore', limit: int = 50000, mode: str = 'occurrence'):
    limit = max(500, min(int(limit), 200000))
    try:
        store.poll_new()
        evs = list(store.events)[-limit:]
    except Exception:
        evs = []

    now = datetime.utcnow()
    windows = {
        '30m': 30 * 60,
        '3h': 3 * 3600,
        '24h': 24 * 3600,
    }

    desc = {
        # Decoder-layer errors
        'framing.length_mismatch': 'Frame payload bit-length did not match expected protocol length for the current decoder profile.',
        'decode.invalid_format_id': 'format_id field did not map to a known/valid format definition.',
        'signal.bit_balance_extreme': 'Bitstream ones/zeros ratio was highly imbalanced, indicating likely demod distortion or false frame lock.',
        'signal.low_snr_proxy': 'SNR proxy heuristic reported low quality for this frame candidate.',
        'decode.zero_payload': 'Decoded payload bits were all zeros; usually indicates bad lock or corrupted symbol decisions.',
        'decode.zero_sensor_id': 'Decoded sensor_id resolved to 0 (commonly symbol timing/bit alignment error).',

        # Framing/timing-layer errors (emitted by upstream framing stage)
        'framing.word_start_stop_mismatch': 'Word-level framing check failed: start/stop bit pattern mismatch in one or more words.',
        'timing.hunt_timeout': 'Timing recovery did not lock within hunt window; frame candidate timed out before stable symbol alignment.',

        # Dynamic fixed-pair mismatch variants (decode.fixed_pair_mismatch_wN)
        'decode.fixed_pair_mismatch': 'Fixed-pair protocol check failed at one or more configured word positions.',
    }

    counts = {}
    packet_totals = {'30m': 0, '3h': 0, '24h': 0}
    packet_with_err = {'30m': 0, '3h': 0, '24h': 0}

    mode = (mode or 'occurrence').strip().lower()
    if mode not in ('occurrence', 'primary_packet'):
        mode = 'occurrence'

    for ev in evs:
        ts = ev.get('ts')
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(str(ts).replace('Z', '+00:00')).replace(tzinfo=None)
        except Exception:
            continue
        age = (now - t).total_seconds()
        errs = ev.get('errors') or []

        active_windows = [wk for wk, sec in windows.items() if age <= sec]
        if not active_windows:
            continue
        for wk in active_windows:
            packet_totals[wk] += 1
            if errs:
                packet_with_err[wk] += 1

        if not errs:
            continue

        if mode == 'primary_packet':
            errs = [errs[0]]

        for er in errs:
            code = str((er or {}).get('code', '')).strip() or 'unknown'
            c = counts.setdefault(code, {'30m': 0, '3h': 0, '24h': 0})
            for wk in active_windows:
                c[wk] += 1

    def describe(code: str):
        if code in desc:
            return desc[code]
        if code.startswith('decode.fixed_pair_mismatch_w'):
            return 'Fixed-pair protocol check failed for this specific word index; compare against configured fixed-pair pattern variant.'
        if code.startswith('decode.fixed_pair_mismatch'):
            return desc['decode.fixed_pair_mismatch']
        return 'No description yet. Add protocol-specific note as decoder rules evolve.'

    rows = []
    total_30m = sum(v['30m'] for v in counts.values())
    total_3h = sum(v['3h'] for v in counts.values())
    total_24h = sum(v['24h'] for v in counts.values())

    def pct(v, t):
        return round((100.0 * v / t), 3) if t > 0 else 0.0

    for code, c in sorted(counts.items(), key=lambda kv: (-kv[1]['24h'], kv[0])):
        rows.append({
            'code': code,
            'count_30m': c['30m'],
            'count_3h': c['3h'],
            'count_24h': c['24h'],
            'pct_30m': pct(c['30m'], total_30m),
            'pct_3h': pct(c['3h'], total_3h),
            'pct_24h': pct(c['24h'], total_24h),
            'description': describe(code),
        })

    return {
        'schema': 'fwlab.error_stats.v1',
        'ts': now.isoformat() + 'Z',
        'sample_limit': limit,
        'mode': mode,
        'counting_note': ('Error-occurrence based (packet may contribute multiple errors)' if mode == 'occurrence' else 'Primary-error-per-packet (max one counted error per packet)'),
        'error_types': len(rows),
        'totals': {
            'count_30m': total_30m,
            'count_3h': total_3h,
            'count_24h': total_24h,
        },
        'packet_totals': packet_totals,
        'packet_with_errors': packet_with_err,
        'rows': rows,
    }


def _anomaly_stats(store: 'EventStore', limit: int = 4000):
    limit = max(100, min(int(limit), 50000))
    try:
        store.poll_new()
        evs = list(store.events)[-limit:]
    except Exception:
        evs = []

    total = 0
    zero_sid = 0
    zero_val = 0
    sid_8191 = 0
    val_2047 = 0
    tuple_8191_2047 = 0

    for ev in evs:
        de = (ev or {}).get('decode') or {}
        if 'sensor_id' not in de and 'data_val' not in de:
            continue
        total += 1
        sid = de.get('sensor_id')
        val = de.get('data_val')
        try:
            sid_i = int(sid)
        except Exception:
            sid_i = None
        try:
            val_i = int(val)
        except Exception:
            val_i = None

        if sid_i == 0:
            zero_sid += 1
        if val_i == 0:
            zero_val += 1
        if sid_i == 8191:
            sid_8191 += 1
        if val_i == 2047:
            val_2047 += 1
        if sid_i == 8191 and val_i == 2047:
            tuple_8191_2047 += 1

    def pct(x):
        return round((100.0 * x / total), 3) if total > 0 else 0.0

    return {
        'schema': 'fwlab.anomaly_stats.v1',
        'ts': datetime.utcnow().isoformat() + 'Z',
        'sample_limit': limit,
        'decoded_frames': total,
        'counts': {
            'sensor_id_0': zero_sid,
            'data_val_0': zero_val,
            'sensor_id_8191': sid_8191,
            'data_val_2047': val_2047,
            'tuple_8191_2047': tuple_8191_2047,
        },
        'pct': {
            'sensor_id_0': pct(zero_sid),
            'data_val_0': pct(zero_val),
            'sensor_id_8191': pct(sid_8191),
            'data_val_2047': pct(val_2047),
            'tuple_8191_2047': pct(tuple_8191_2047),
        },
        'acceptance_targets': {
            'reduce_sensor_id_0': True,
            'reduce_data_val_0': True,
            'reduce_sensor_id_8191': True,
            'reduce_data_val_2047': True,
            'reduce_tuple_8191_2047': True,
        }
    }


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


def render_bitflipper_html():
    art = "<div class='muted'>No image loaded (expected uploads/file_drop/image_bitflipper.svg).</div>"
    p = FILE_DROP_DIR / 'image_bitflipper.svg'
    if p.exists():
        try:
            raw = p.read_text(encoding='utf-8', errors='replace')
            if '<svg' in raw.lower():
                art = f"<div class='bf-art'>{raw}</div>"
            else:
                art = "<div class='muted'>image_bitflipper.svg found but is not valid SVG text.</div>"
        except Exception as e:
            art = f"<div class='muted'>Failed to load image_bitflipper.svg: {html.escape(str(e))}</div>"
    return BITFLIPPER_HTML.replace('__NAV__', NAV_HTML).replace('__BITFLIPPER_ART__', art)


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
<div class='muted'>This page mirrors README.md from the running repo so operators can verify behavior against current docs. Use it for release notes, setup references, and implementation context.</div>
</div>
<div class='card'><div class='md'>{rendered}</div></div>
</div></body></html>"""


def load_control_plane_policy(path='config/control_plane_policy.json'):
    p = Path(path)
    default = {
        'schema': 'fwlab.control_policy.v1',
        'enabled': False,
        'ingestToken': '',
        'allowLocalhostWithoutToken': True,
        'maxEventsPerIngest': 5000,
        'ingestStateDir': 'rf_log/control_ingest',
    }
    if not p.exists():
        return default
    try:
        d = json.loads(p.read_text(encoding='utf-8', errors='replace'))
        if not isinstance(d, dict):
            return default
        out = dict(default)
        out.update(d)
        out['enabled'] = bool(out.get('enabled', False))
        out['ingestToken'] = str(out.get('ingestToken', ''))
        out['allowLocalhostWithoutToken'] = bool(out.get('allowLocalhostWithoutToken', True))
        out['maxEventsPerIngest'] = int(out.get('maxEventsPerIngest', 5000) or 5000)
        out['ingestStateDir'] = str(out.get('ingestStateDir', 'rf_log/control_ingest') or 'rf_log/control_ingest')
        return out
    except Exception:
        return default


def control_ingest_authorized(headers, remote_addr: str) -> bool:
    pol = load_control_plane_policy()
    if not bool(pol.get('enabled', False)):
        return True
    if bool(pol.get('allowLocalhostWithoutToken', True)) and is_local_request(remote_addr):
        return True
    expected = str(pol.get('ingestToken', ''))
    supplied = str(headers.get('X-Control-Token', ''))
    return bool(expected) and (supplied == expected)


def _control_ingest_paths():
    pol = load_control_plane_policy()
    base = Path(str(pol.get('ingestStateDir', 'rf_log/control_ingest')))
    latest = base / 'latest'
    by_rx = base / 'by_receiver'
    latest.mkdir(parents=True, exist_ok=True)
    by_rx.mkdir(parents=True, exist_ok=True)
    return base, latest, by_rx


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


def _bootstrap_meta_catalog():
    stations = []
    sensors = []
    try:
        src = Path('config/stations_catalog.csv') if Path('config/stations_catalog.csv').exists() else Path('config/stations.csv')
        if src.exists():
            with src.open('r', encoding='utf-8', errors='replace', newline='') as fh:
                rdr = csv.DictReader(fh)
                for r in rdr:
                    stations.append({
                        'station_key': str((r.get('unitid') or r.get('site_id_bom') or r.get('unitname') or '')).strip(),
                        'rxs_id': None,
                        'bom_stn': str((r.get('unitid') or r.get('site_id_bom') or '')).strip(),
                        'name': str((r.get('unitname') or r.get('name') or '')).strip(),
                        'location': str((r.get('location') or r.get('unitname') or '')).strip(),
                        'lat': r.get('latitude', ''),
                        'lon': r.get('longitude', ''),
                        'elevation_m': r.get('elevation', ''),
                        'arro_site_id': str(r.get('arro_site_id', '')).strip(),
                        'enabled': True,
                        'active': True,
                        'tags': [],
                        'notes': '',
                    })
    except Exception:
        pass
    try:
        smp = Path('config/sensor_map.csv')
        if smp.exists():
            with smp.open('r', encoding='utf-8', errors='replace', newline='') as fh:
                rdr = csv.DictReader(fh)
                for r in rdr:
                    sid = str(r.get('Sensor ID', '')).strip()
                    alert1 = sid.split('.')[-1] if sid else ''
                    sensors.append({
                        'sensor_key': sid or alert1,
                        'station_bom_stn': str(r.get('Site ID', '')).strip(),
                        'sensor_type': str(r.get('Sensor', '')).strip(),
                        'sensor_id': sid,
                        'alert1_id': alert1,
                        'device_id': str(r.get('device_id', '')).strip(),
                        'arro_site_id': str(r.get('site_id', '')).strip(),
                        'active': True,
                        'notes': '',
                    })
    except Exception:
        pass
    return {'schema': 'fwlab.meta.catalog.v1', 'stations': stations, 'sensors': sensors}


def load_meta_catalog(path='config/meta_catalog.json'):
    p = Path(path)
    if not p.exists():
        cat = _bootstrap_meta_catalog()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cat, indent=2) + '\n', encoding='utf-8')
        return cat
    try:
        d = json.loads(p.read_text(encoding='utf-8', errors='replace'))
        if not isinstance(d, dict):
            return {'schema': 'fwlab.meta.catalog.v1', 'stations': [], 'sensors': []}
        d.setdefault('schema', 'fwlab.meta.catalog.v1')
        d.setdefault('stations', [])
        d.setdefault('sensors', [])
        return d
    except Exception:
        return {'schema': 'fwlab.meta.catalog.v1', 'stations': [], 'sensors': []}


def save_meta_catalog(cat: dict, path='config/meta_catalog.json'):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cat, indent=2) + '\n', encoding='utf-8')


def snapshot_meta_catalog(cat: dict, reason: str = 'update'):
    try:
        ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        d = Path('rf_log/audit/meta_catalog')
        d.mkdir(parents=True, exist_ok=True)
        out = d / f'{ts}_{reason}.json'
        out.write_text(json.dumps(cat, indent=2) + '\n', encoding='utf-8')
        return str(out)
    except Exception:
        return ''


def meta_history_append(action: str, details: dict | None = None):
    try:
        p = Path('rf_log/audit/meta_catalog_history.jsonl')
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'action': action,
            'details': details or {},
        }
        with p.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(rec) + '\n')
    except Exception:
        pass


def load_deployment_role(path='config/deployment_role.json'):
    p = Path(path)
    default = {
        'schema': 'fwlab.deployment_role.v1',
        'role': 'edge',
        'receiver': {'rxs_id': '0000', 'name': 'FW-LAB Receiver', 'location': 'unknown'},
        'control': {'enabled': False, 'state_backend': 's3', 'state_prefix': 'fwlab/control-plane'},
    }
    if not p.exists():
        return default
    try:
        d = json.loads(p.read_text(encoding='utf-8', errors='replace'))
        if not isinstance(d, dict):
            return default
        out = dict(default)
        out.update(d)
        return out
    except Exception:
        return default


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


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1 = math.radians(float(lat1)); p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1-a)))


def _fspl_db(distance_km, freq_mhz):
    d = max(float(distance_km), 1e-6)
    f = max(float(freq_mhz), 1e-6)
    return 32.44 + 20*math.log10(d) + 20*math.log10(f)


def _line_points(lat1, lon1, lat2, lon2, n):
    pts = []
    for i in range(n):
        t = i / max(1, n - 1)
        pts.append((lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t))
    return pts


def _terrain_from_opentopodata(points, dataset='srtm90m'):
    # Public API; best-effort only. Returns list or None.
    vals = []
    try:
        chunk = 90
        for i in range(0, len(points), chunk):
            part = points[i:i+chunk]
            loc = '|'.join([f"{lat:.6f},{lon:.6f}" for lat, lon in part])
            url = f"https://api.opentopodata.org/v1/{dataset}?locations={quote(loc, safe='|,.-')}"
            with urllib.request.urlopen(url, timeout=8) as resp:
                d = json.loads(resp.read().decode('utf-8', errors='replace'))
            rs = d.get('results') or []
            if len(rs) != len(part):
                return None
            for r in rs:
                e = r.get('elevation')
                vals.append(float(e) if e is not None else 0.0)
        return vals
    except Exception:
        return None


def _path_compare(req):
    out = _path_analyze(req)
    measured = req.get('measured') or {}
    rx_meas = measured.get('rx_dbm')
    if rx_meas is not None:
        try:
            rx_meas = float(rx_meas)
            pred = float((out.get('summary') or {}).get('predicted_rx_dbm'))
            delta = pred - rx_meas
            parity = out.setdefault('parity', {})
            parity['measured_rx_dbm'] = rx_meas
            parity['delta_db'] = round(delta, 3)
            parity['fit_class'] = 'good' if abs(delta) <= 3 else ('ok' if abs(delta) <= 6 else 'poor')
        except Exception:
            pass
    return out


def _path_analyze(req):
    tx = req.get('tx') or {}
    rx = req.get('rx') or {}
    rf = req.get('rf') or {}
    model = req.get('model') or {}
    sampling = req.get('sampling') or {}

    required = [
        ('tx.lat', tx.get('lat')), ('tx.lon', tx.get('lon')),
        ('rx.lat', rx.get('lat')), ('rx.lon', rx.get('lon')),
        ('rf.frequency_mhz', rf.get('frequency_mhz')),
        ('rf.tx_power_dbm', rf.get('tx_power_dbm')),
        ('rf.rx_sensitivity_dbm', rf.get('rx_sensitivity_dbm')),
    ]
    miss = [k for k, v in required if v is None or str(v) == '']
    if miss:
        raise ValueError('missing required fields: ' + ', '.join(miss))

    lat1 = float(tx.get('lat')); lon1 = float(tx.get('lon'))
    lat2 = float(rx.get('lat')); lon2 = float(rx.get('lon'))
    tx_agl = float(tx.get('antenna_agl_m', 0.0)); rx_agl = float(rx.get('antenna_agl_m', 0.0))
    freq = float(rf.get('frequency_mhz'))
    tx_pwr = float(rf.get('tx_power_dbm'))
    tx_gain = float(rf.get('tx_antenna_gain_dbi', 0.0)); rx_gain = float(rf.get('rx_antenna_gain_dbi', 0.0))
    tx_loss = float(rf.get('tx_system_loss_db', 0.0)); rx_loss = float(rf.get('rx_system_loss_db', 0.0))
    rx_sens = float(rf.get('rx_sensitivity_dbm'))

    distance_km = _haversine_km(lat1, lon1, lat2, lon2)

    step_m = max(10.0, float(sampling.get('profile_step_m', 100.0)))
    total_m = max(distance_km * 1000.0, 1.0)
    points = min(int(sampling.get('max_points', 2000)), max(8, int(total_m / step_m) + 1))
    points = max(8, min(points, 2000))
    dists = [i * (total_m / (points - 1)) for i in range(points)]

    warnings = []
    terrain_mode = 'flat_base'
    terrain_override = sampling.get('terrain_profile_m_asl')
    if isinstance(terrain_override, list) and len(terrain_override) >= 2:
        terrain_mode = 'override_profile'
        src = [float(x) for x in terrain_override]
        terrain = []
        for i in range(points):
            j = int(round(i * (len(src) - 1) / max(1, points - 1)))
            terrain.append(src[j])
    else:
        provider = str(sampling.get('terrain_provider', 'flat')).strip().lower()
        if provider in ('opentopodata', 'srtm90m'):
            terrain_mode = 'opentopodata_srtm90m'
            # keep API workload reasonable for MVP
            points_api = min(points, 200)
            pts = _line_points(lat1, lon1, lat2, lon2, points_api)
            terr = _terrain_from_opentopodata(pts, dataset='srtm90m')
            if terr and len(terr) == points_api:
                # resample to analysis point count
                terrain = []
                for i in range(points):
                    j = int(round(i * (points_api - 1) / max(1, points - 1)))
                    terrain.append(float(terr[j]))
            else:
                base_terrain = float(sampling.get('terrain_base_m_asl', 0.0))
                terrain = [base_terrain for _ in dists]
                warnings.append('Terrain provider failed/unavailable; fell back to flat base terrain.')
                terrain_mode = 'flat_base_fallback'
        else:
            base_terrain = float(sampling.get('terrain_base_m_asl', 0.0))
            terrain = [base_terrain for _ in dists]

    tx_asl = terrain[0] + tx_agl
    rx_asl = terrain[-1] + rx_agl
    los = [tx_asl + (rx_asl - tx_asl) * (i / (points - 1)) for i in range(points)]

    fres = []
    for di in dists:
        d1 = max(di, 0.001); d2 = max(total_m - di, 0.001)
        # Fresnel radius (meters), with distances in km and frequency in MHz:
        # r_n = sqrt(n * lambda * d1 * d2 / (d1 + d2)), lambda = 300 / f_MHz (m)
        # => r1(m) = 547.72 * sqrt(d1_km * d2_km / (f_MHz * D_km))
        fres.append(547.72 * math.sqrt((d1/1000.0)*(d2/1000.0)/(max(freq,1e-6)*(total_m/1000.0))))

    clearance = [l - t for l, t in zip(los, terrain)]
    fresnel60_clear = [c - 0.6*f for c, f in zip(clearance, fres)]
    min_f60 = min(fresnel60_clear) if fresnel60_clear else 0.0

    fspl = _fspl_db(distance_km, freq)
    mode = str(model.get('mode', 'fspl_mvp')).strip().lower() or 'fspl_mvp'
    diff_penalty = 0.0
    if mode == 'fspl_diffraction_proxy' and min_f60 < 0:
        diff_penalty = min(30.0, abs(min_f60) * 0.8)

    path_loss = fspl + diff_penalty
    predicted_rx = tx_pwr + tx_gain - tx_loss - path_loss + rx_gain - rx_loss
    fade_margin = predicted_rx - rx_sens
    margin_class = 'good' if fade_margin >= 20 else ('marginal' if fade_margin >= 10 else 'poor')

    return {
        'schema': 'fwlab.path.result.v1',
        'ts': datetime.utcnow().isoformat() + 'Z',
        'request_schema': 'fwlab.path.request.v1',
        'summary': {
            'distance_km': round(distance_km, 4),
            'path_loss_db': round(path_loss, 3),
            'fspl_db': round(fspl, 3),
            'diffraction_proxy_db': round(diff_penalty, 3),
            'predicted_rx_dbm': round(predicted_rx, 3),
            'fade_margin_db': round(fade_margin, 3),
            'margin_class': margin_class,
        },
        'budget': {
            'tx_power_dbm': tx_pwr,
            'tx_antenna_gain_dbi': tx_gain,
            'tx_system_loss_db': tx_loss,
            'path_loss_db': round(path_loss, 3),
            'fspl_db': round(fspl, 3),
            'diffraction_proxy_db': round(diff_penalty, 3),
            'rx_antenna_gain_dbi': rx_gain,
            'rx_system_loss_db': rx_loss,
            'predicted_rx_dbm': round(predicted_rx, 3),
            'rx_sensitivity_dbm': rx_sens,
            'fade_margin_db': round(fade_margin, 3),
        },
        'profile': {
            'distance_m': [round(x, 2) for x in dists],
            'terrain_m_asl': terrain,
            'los_m_asl': [round(x, 3) for x in los],
            'fresnel60_radius_m': [round(x, 3) for x in fres],
            'clearance_m': [round(c, 3) for c in clearance],
            'fresnel60_clearance_m': [round(x, 3) for x in fresnel60_clear],
        },
        'assumptions': {
            'propagation_model': mode,
            'terrain_mode': terrain_mode,
            'fresnel60_min_clearance_m': round(min_f60, 3),
            'note': 'Diffraction proxy mode is interim; Radio Mobile parity calibration still pending.',
        },
        'warnings': (warnings + ([] if mode == 'fspl_diffraction_proxy' else ['Using FSPL-only baseline. Select fspl_diffraction_proxy for interim terrain obstruction penalty.']))
    }


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


def _resolve_chunk_path(ent):
    cp = Path(str(ent.get('chunk_path', '')))
    if cp.exists():
        return cp
    # Off-prem mirror fallback: use local archive_state/chunks by basename.
    b = cp.name
    if b:
        local_cp = Path('rf_log/archive_state/chunks') / b
        if local_cp.exists():
            return local_cp
    return None


def sensor_ids_from_archive(limit_entries: int = 200):
    ids = set()
    entries = [e for e in _archive_manifest() if e.get('status') == 'uploaded' and e.get('chunk_path')]
    for ent in entries[-max(1, limit_entries):]:
        cp = _resolve_chunk_path(ent)
        if not cp:
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


def merge_points(local_points, archive_points, limit: int):
    by_ts = {}
    for p in archive_points or []:
        ts = p.get('ts')
        if ts:
            by_ts[ts] = {'ts': ts, 'value': float(p.get('value', 0.0))}
    for p in local_points or []:
        ts = p.get('ts')
        if ts:
            by_ts[ts] = {'ts': ts, 'value': float(p.get('value', 0.0))}
    out = sorted(by_ts.values(), key=lambda p: p['ts'])
    return out[-limit:]


_ARCHIVE_TRENDS_CACHE = {}


def trends_from_archive(sensor_id: str, win: str, limit: int):
    now = time.time()
    manifest_path = Path('rf_log/archive_state/manifest.json')
    mtime = manifest_path.stat().st_mtime if manifest_path.exists() else 0
    ck = (str(sensor_id), str(win), int(limit), int(mtime))
    cached = _ARCHIVE_TRENDS_CACHE.get(ck)
    if cached and (now - cached.get('ts', 0) < 30):
        return cached['value']

    cutoff = now - window_seconds(win)
    entries = [e for e in _archive_manifest() if e.get('status') == 'uploaded' and e.get('chunk_path')]
    entries = sorted(entries, key=lambda e: e.get('first_ts') or '')

    points = []
    src = 'archive:none'
    for ent in entries:
        cp = _resolve_chunk_path(ent)
        if not cp:
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
    out = {'points': points, 'stats': stats, 'source': src}
    _ARCHIVE_TRENDS_CACHE[ck] = {'ts': now, 'value': out}
    return out


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
        if parsed.path in ['/api/path/analyze', '/api/path/compare']:
            try:
                length = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(length) if length > 0 else b'{}'
                body = json.loads(raw.decode('utf-8'))
                if not isinstance(body, dict):
                    raise ValueError('body must be object')
                out = _path_compare(body) if parsed.path.endswith('/compare') else _path_analyze(body)
                return self._json(out)
            except Exception as e:
                return self._json({'ok': False, 'error': str(e)}, code=400)

        if parsed.path == '/api/path/defaults':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(length) if length > 0 else b'{}'
                body = json.loads(raw.decode('utf-8', errors='replace'))
                if not isinstance(body, dict):
                    return self._json({'ok': False, 'error': 'body must be object'}, code=400)
                _save_path_defaults(body)
                return self._json({'ok': True, 'source': str(PATH_DEFAULTS_PATH)})
            except Exception as e:
                return self._json({'ok': False, 'error': str(e)}, code=400)

        if parsed.path == '/api/stations/update':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(length) if length > 0 else b'{}'
                body = json.loads(raw.decode('utf-8', errors='replace'))
                idx = int(body.get('index'))
                rows = _load_stations(limit=100000)
                if idx < 0 or idx >= len(rows):
                    return self._json({'ok': False, 'error': 'index_out_of_range'}, code=400)
                r = rows[idx]
                key = str(r.get('station_key', '') or r.get('unitid', '') or r.get('name', '')).strip()
                nm = str(body.get('name', '')).strip()
                lat = str(body.get('lat', '')).strip()
                lon = str(body.get('lon', '')).strip()
                elev = str(body.get('elevation', '')).strip()
                enabled = str(body.get('enabled', '')).strip()

                cat = load_meta_catalog('config/meta_catalog.json')
                arr = cat.get('stations', [])
                pos = next((i for i, s in enumerate(arr) if str(s.get('station_key', '')).strip() == key), -1)
                item = arr[pos] if pos >= 0 else {
                    'station_key': key,
                    'bom_stn': str(r.get('unitid', '')).strip(),
                    'name': str(r.get('name', '') or r.get('unitname', '')).strip(),
                    'location': str(r.get('location', '') or r.get('name', '') or r.get('unitname', '')).strip(),
                    'enabled': True,
                    'active': True,
                }
                if nm:
                    item['name'] = nm
                    item['location'] = nm
                if lat != '':
                    item['lat'] = lat
                if lon != '':
                    item['lon'] = lon
                if elev != '':
                    item['elevation_m'] = elev
                if enabled != '':
                    item['enabled'] = (str(enabled).strip() not in ('0', 'false', 'False', 'no'))
                if pos >= 0:
                    arr[pos] = item
                else:
                    arr.append(item)
                cat['stations'] = arr
                save_meta_catalog(cat, 'config/meta_catalog.json')
                _write_stations_master(_load_stations(limit=100000))
                return self._json({'ok': True, 'index': idx, 'station_key': key})
            except Exception as e:
                return self._json({'ok': False, 'error': str(e)}, code=400)

        if parsed.path == '/api/stations/delete':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(length) if length > 0 else b'{}'
                body = json.loads(raw.decode('utf-8', errors='replace'))
                idx = int(body.get('index'))
                rows = _load_stations(limit=100000)
                if idx < 0 or idx >= len(rows):
                    return self._json({'ok': False, 'error': 'index_out_of_range'}, code=400)
                r = rows[idx]
                key = str(r.get('station_key', '') or r.get('unitid', '') or r.get('name', '')).strip()
                cat = load_meta_catalog('config/meta_catalog.json')
                arr = cat.get('stations', [])
                n = len(arr)
                arr = [s for s in arr if str(s.get('station_key', '')).strip() != key]
                cat['stations'] = arr
                save_meta_catalog(cat, 'config/meta_catalog.json')
                _write_stations_master(_load_stations(limit=100000))
                return self._json({'ok': True, 'deleted': n-len(arr), 'station_key': key})
            except Exception as e:
                return self._json({'ok': False, 'error': str(e)}, code=400)

        if parsed.path == '/api/stations/upload':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(length) if length > 0 else b'{}'
                body = json.loads(raw.decode('utf-8', errors='replace'))
                txt = str(body.get('csv_text', ''))
                if not txt.strip():
                    return self._json({'ok': False, 'error': 'empty_csv'}, code=400)
                parsed_rows = _parse_stations_csv_text(txt, limit=50000)
                if not parsed_rows:
                    return self._json({'ok': False, 'error': 'parse_failed_no_rows', 'hint': 'check delimiter/header includes Latitude/Longitude'}, code=400)
                STATIONS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
                STATIONS_CSV_PATH.write_text(txt, encoding='utf-8')
                _write_stations_master(_load_stations(limit=100000))
                return self._json({'ok': True, 'count': len(parsed_rows), 'source': str(STATIONS_CSV_PATH)})
            except Exception as e:
                return self._json({'ok': False, 'error': str(e)}, code=400)

        if parsed.path == '/api/file_drop/upload':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(length) if length > 0 else b'{}'
                body = json.loads(raw.decode('utf-8', errors='replace'))
                fn = os.path.basename(str(body.get('filename', 'upload.txt')).strip() or 'upload.txt')
                content = str(body.get('content', ''))
                FILE_DROP_DIR.mkdir(parents=True, exist_ok=True)
                outp = FILE_DROP_DIR / fn
                outp.write_text(content, encoding='utf-8', errors='replace')
                ftype = 'generic'
                mapped = 0
                # auto-capture station/sensor mapping file shape
                low = fn.lower()
                if low.endswith('.csv') and _looks_like_sensor_map_csv(content):
                    SENSOR_MAP_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
                    SENSOR_MAP_CSV_PATH.write_text(content, encoding='utf-8', errors='replace')
                    ftype = 'sensor_map'
                    mapped = len(_load_sensor_map())
                    _write_stations_master(_load_stations(limit=100000))
                return self._json({'ok': True, 'path': str(outp), 'type': ftype, 'mapped_alert1_ids': mapped})
            except Exception as e:
                return self._json({'ok': False, 'error': str(e)}, code=400)

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

        if parsed.path == '/api/control/ingest':
            ra = self.client_address[0] if self.client_address else ''
            if not control_ingest_authorized(self.headers, ra):
                return self._json({'ok': False, 'error': 'unauthorized'}, code=403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(length) if length > 0 else b'{}'
                body = json.loads(raw.decode('utf-8', errors='replace'))
                if not isinstance(body, dict):
                    raise ValueError('body must be object')
                rxs_id = str(body.get('rxs_id', '')).strip().upper()
                if not _is_valid_rxs_id(rxs_id):
                    return self._json({'ok': False, 'error': 'invalid_rxs_id'}, code=400)
                pol = load_control_plane_policy()
                max_events = max(1, min(int(pol.get('maxEventsPerIngest', 5000)), 20000))
                events = body.get('events', [])
                if not isinstance(events, list):
                    events = []
                events = events[:max_events]
                heartbeat = body.get('heartbeat', {}) if isinstance(body.get('heartbeat', {}), dict) else {}
                stats = body.get('stats', {}) if isinstance(body.get('stats', {}), dict) else {}
                rec = {
                    'ts': datetime.utcnow().isoformat() + 'Z',
                    'rxs_id': rxs_id,
                    'remote_addr': ra,
                    'events': events,
                    'event_count': len(events),
                    'heartbeat': heartbeat,
                    'stats': stats,
                }
                base, latest_dir, by_rx = _control_ingest_paths()
                day = datetime.utcnow().strftime('%Y-%m-%d')
                out = by_rx / f'{rxs_id}_{day}.jsonl'
                with out.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(rec) + '\n')
                (latest_dir / f'{rxs_id}.json').write_text(json.dumps(rec, indent=2) + '\n', encoding='utf-8')
                return self._json({'ok': True, 'rxs_id': rxs_id, 'event_count': len(events), 'path': str(out)})
            except Exception as e:
                return self._json({'ok': False, 'error': str(e)}, code=400)

        if parsed.path in ['/api/admin/storage_policy', '/api/admin/rf_control', '/api/admin/receiver_action', '/api/admin/meta/catalog']:
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

                if parsed.path == '/api/admin/meta/catalog':
                    cat = load_meta_catalog()
                    entity = str(body.get('entity', '')).strip().lower()  # station|sensor
                    op = str(body.get('op', '')).strip().lower()  # upsert|delete
                    item = body.get('item', {}) or {}
                    if entity not in ('station', 'sensor') or op not in ('upsert', 'delete'):
                        return self._json({'ok': False, 'error': 'invalid entity/op'}, code=400)
                    key_field = 'station_key' if entity == 'station' else 'sensor_key'
                    key = str(item.get(key_field, body.get(key_field, ''))).strip()
                    arr = cat['stations'] if entity == 'station' else cat['sensors']
                    idx = next((i for i, r in enumerate(arr) if str(r.get(key_field, '')).strip() == key), -1)
                    if op == 'delete':
                        if idx >= 0:
                            arr.pop(idx)
                        snap = snapshot_meta_catalog(cat, f'{entity}_delete')
                        save_meta_catalog(cat)
                        meta_history_append('delete', {'entity': entity, key_field: key, 'snapshot': snap})
                        audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', True, {'entity': entity, 'op': op, key_field: key})
                        return self._json({'ok': True, 'entity': entity, 'op': op, key_field: key, 'snapshot': snap})
                    # upsert
                    if not key:
                        return self._json({'ok': False, 'error': f'missing {key_field}'}, code=400)
                    if idx >= 0:
                        arr[idx].update(item)
                    else:
                        arr.append(item)
                    snap = snapshot_meta_catalog(cat, f'{entity}_upsert')
                    save_meta_catalog(cat)
                    meta_history_append('upsert', {'entity': entity, key_field: key, 'snapshot': snap})
                    audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', True, {'entity': entity, 'op': op, key_field: key})
                    return self._json({'ok': True, 'entity': entity, 'op': op, key_field: key, 'snapshot': snap})

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

    def do_HEAD(self):
        parsed = urlparse(self.path)
        html_paths = {
            '/', '/events', '/packets', '/overview', '/help', '/trends', '/data', '/path', '/stations', '/stations-map', '/map',
            '/trip', '/file_drop', '/bitflipper', '/radio', '/forensics', '/about', '/admin'
        }
        if parsed.path in html_paths:
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if parsed.path.startswith('/api/'):
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ['/', '/events', '/packets']:
            payload = HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/overview':
            payload = OVERVIEW_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/help':
            payload = HELP_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path in ['/trends', '/data']:
            payload = TRENDS_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/path':
            payload = PATH_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/stations':
            payload = STATIONS_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path in ['/stations-map', '/map']:
            payload = STATIONS_MAP_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/trip':
            payload = TRIP_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/file_drop':
            payload = FILE_DROP_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == '/bitflipper':
            payload = render_bitflipper_html().encode('utf-8')
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
                audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', False, {'error': 'unauthorized'})
                return self._json({'ok': False, 'error': 'unauthorized'}, code=403)
            audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', True, {})
            return self._json(load_storage_policy())

        if parsed.path == '/api/admin/rf_control':
            if not admin_authorized(self.headers, self.client_address[0] if self.client_address else ''):
                audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', False, {'error': 'unauthorized'})
                return self._json({'ok': False, 'error': 'unauthorized'}, code=403)
            audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', True, {})
            return self._json(load_rf_control())

        if parsed.path == '/api/admin/audit_recent':
            if not admin_authorized(self.headers, self.client_address[0] if self.client_address else ''):
                audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', False, {'error': 'unauthorized'})
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
            audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', True, {'limit': limit})
            return self._json({'events': rows, 'count': len(rows)})

        if parsed.path == '/api/admin/meta/history':
            if not admin_authorized(self.headers, self.client_address[0] if self.client_address else ''):
                audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', False, {'error': 'unauthorized'})
                return self._json({'ok': False, 'error': 'unauthorized'}, code=403)
            q = parse_qs(parsed.query)
            limit = int(q.get('limit', ['100'])[0])
            limit = max(1, min(limit, 500))
            p = Path('rf_log/audit/meta_catalog_history.jsonl')
            rows = []
            if p.exists():
                for line in p.read_text(encoding='utf-8', errors='replace').splitlines()[-limit:]:
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
            audit_admin_action(parsed.path, self.client_address[0] if self.client_address else '', True, {'limit': limit})
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

        if parsed.path == '/api/pair_pattern_stats':
            q = parse_qs(parsed.query)
            limit = int(q.get('limit', ['2000'])[0])
            return self._json(_pair_pattern_stats(self.store, limit=limit))

        if parsed.path == '/api/error_stats':
            q = parse_qs(parsed.query)
            limit = int(q.get('limit', ['50000'])[0])
            mode = str(q.get('mode', ['occurrence'])[0])
            return self._json(_error_stats(self.store, limit=limit, mode=mode))

        if parsed.path == '/api/anomaly_stats':
            q = parse_qs(parsed.query)
            limit = int(q.get('limit', ['4000'])[0])
            return self._json(_anomaly_stats(self.store, limit=limit))

        if parsed.path == '/api/rx_agg':
            if RX_AGG_JSON_PATH.exists():
                try:
                    d = json.loads(RX_AGG_JSON_PATH.read_text(encoding='utf-8', errors='replace'))
                    d['source'] = str(RX_AGG_JSON_PATH)
                    return self._json(d)
                except Exception as e:
                    return self._json({'error': f'parse_failed: {e}', 'source': str(RX_AGG_JSON_PATH)}, code=500)
            return self._json({'error': 'not_ready', 'source': str(RX_AGG_JSON_PATH)}, code=404)

        if parsed.path == '/api/receiver_info':
            info = _load_receiver_identity()
            info['source'] = str(RECEIVER_IDENTITY_PATH)
            return self._json(info)

        if parsed.path == '/api/receivers_registry':
            reg = _load_receivers_registry()
            reg['source'] = str(RECEIVERS_REGISTRY_PATH)
            return self._json(reg)

        if parsed.path in ['/api/meta/catalog', '/api/meta/export']:
            cat = load_meta_catalog()
            cat['source'] = 'config/meta_catalog.json'
            return self._json(cat)

        if parsed.path == '/api/deployment_role':
            d = load_deployment_role()
            d['source'] = 'config/deployment_role.json'
            return self._json(d)

        if parsed.path == '/api/control/policy':
            pol = load_control_plane_policy()
            pol.pop('ingestToken', None)
            return self._json(pol)

        if parsed.path == '/api/control/receivers':
            _, latest_dir, _ = _control_ingest_paths()
            rows = []
            for p in sorted(latest_dir.glob('*.json')):
                try:
                    d = json.loads(p.read_text(encoding='utf-8', errors='replace'))
                    rows.append({
                        'rxs_id': str(d.get('rxs_id', '')).strip().upper(),
                        'last_ts': d.get('ts', ''),
                        'event_count': int(d.get('event_count', 0) or 0),
                        'heartbeat': d.get('heartbeat', {}),
                        'stats': d.get('stats', {}),
                    })
                except Exception:
                    pass
            return self._json({'receivers': rows, 'count': len(rows)})

        if parsed.path == '/api/control/receiver_latest':
            q = parse_qs(parsed.query)
            rxs_id = str((q.get('rxs_id', [''])[0] or '')).strip().upper()
            if not _is_valid_rxs_id(rxs_id):
                return self._json({'ok': False, 'error': 'invalid_rxs_id'}, code=400)
            _, latest_dir, _ = _control_ingest_paths()
            p = latest_dir / f'{rxs_id}.json'
            if not p.exists():
                return self._json({'ok': False, 'error': 'not_found'}, code=404)
            try:
                d = json.loads(p.read_text(encoding='utf-8', errors='replace'))
                return self._json({'ok': True, 'data': d})
            except Exception as e:
                return self._json({'ok': False, 'error': str(e)}, code=500)

        if parsed.path == '/api/receiver_proxy':
            q = parse_qs(parsed.query)
            rxs_id = str((q.get('rxs_id', [''])[0] or '')).strip().upper()
            subpath = str((q.get('path', [''])[0] or '')).strip()
            if not _is_valid_rxs_id(rxs_id):
                return self._json({'ok': False, 'error': 'invalid_rxs_id'}, code=400)
            if not subpath.startswith('/api/'):
                return self._json({'ok': False, 'error': 'path_must_start_api'}, code=400)
            reg = _load_receivers_registry()
            rx = next((r for r in (reg.get('receivers') or []) if str(r.get('rxs_id', '')).strip().upper() == rxs_id), None)
            if not rx:
                return self._json({'ok': False, 'error': 'receiver_not_found'}, code=404)
            base = str(rx.get('base_url', 'local') or 'local').strip()
            if base in ('', 'local'):
                return self._json({'ok': False, 'error': 'receiver_is_local_use_direct'}, code=400)
            try:
                url = base.rstrip('/') + subpath
                with urllib.request.urlopen(url, timeout=10) as resp:
                    raw = resp.read().decode('utf-8', errors='replace')
                try:
                    obj = json.loads(raw)
                except Exception:
                    obj = {'raw': raw}
                return self._json({'ok': True, 'rxs_id': rxs_id, 'path': subpath, 'data': obj})
            except Exception as e:
                return self._json({'ok': False, 'error': str(e)}, code=502)

        if parsed.path == '/api/stations':
            rows = _load_stations()
            pairs = _pairs_within_km(rows, max_km=100.0, limit=5000)
            return self._json({'count': len(rows), 'pairs_100km': pairs, 'source': str(STATIONS_CSV_PATH)})

        if parsed.path == '/api/path/defaults':
            d = _load_path_defaults()
            return self._json({'ok': True, 'defaults': d, 'source': str(PATH_DEFAULTS_PATH)})

        if parsed.path == '/api/stations/catalog':
            q = urllib.parse.parse_qs(parsed.query)
            try:
                limit = int((q.get('limit', ['5000'])[0] or '5000'))
            except Exception:
                limit = 5000
            rows = _load_stations(limit=max(1, min(limit, 50000)))
            out = []
            for i, r in enumerate(rows):
                lat, lon = _station_lat_lon(r)
                if lat is None or lon is None:
                    continue
                out.append({'index': i, 'name': _station_name(r, i), 'lat': lat, 'lon': lon})
            return self._json({'count': len(out), 'stations': out, 'source': str(STATIONS_CSV_PATH)})

        if parsed.path == '/api/stations/rows':
            q = urllib.parse.parse_qs(parsed.query)
            try:
                limit = int((q.get('limit', ['5000'])[0] or '5000'))
            except Exception:
                limit = 5000
            rows = _load_stations(limit=max(1, min(limit, 50000)))
            out = []
            for i, r in enumerate(rows):
                rec = dict(r)
                rec['index'] = i
                rec['name'] = _station_name(r, i)
                lat, lon = _station_lat_lon(r)
                rec['latitude'] = '' if lat is None else lat
                rec['longitude'] = '' if lon is None else lon
                out.append(rec)
            return self._json({'count': len(out), 'rows': out, 'source': str(STATIONS_CSV_PATH)})

        if parsed.path == '/api/file_drop/list':
            q = urllib.parse.parse_qs(parsed.query)
            try:
                limit = int((q.get('limit', ['20'])[0] or '20'))
            except Exception:
                limit = 20
            limit = max(1, min(limit, 200))
            FILE_DROP_DIR.mkdir(parents=True, exist_ok=True)
            files = []
            for p in sorted(FILE_DROP_DIR.glob('*'), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                try:
                    st = p.stat()
                    ftype = 'generic'
                    try:
                        txt = p.read_text(encoding='utf-8', errors='replace')[:8000].lower()
                        if p.suffix.lower() == '.csv' and ('sensor id' in txt and 'site id' in txt and 'device_id' in txt):
                            ftype = 'sensor_map_candidate'
                    except Exception:
                        pass
                    files.append({'name': p.name, 'size': st.st_size, 'mtime': datetime.utcfromtimestamp(st.st_mtime).isoformat()+'Z', 'type': ftype})
                except Exception:
                    continue
            return self._json({'count': len(files), 'files': files, 'dir': str(FILE_DROP_DIR), 'sensor_map_path': str(SENSOR_MAP_CSV_PATH), 'sensor_map_exists': SENSOR_MAP_CSV_PATH.exists()})

        if parsed.path == '/api/sensor_map/status':
            sm = _load_sensor_map(limit=100000)
            return self._json({'ok': True, 'path': str(SENSOR_MAP_CSV_PATH), 'exists': SENSOR_MAP_CSV_PATH.exists(), 'mapped_alert1_ids': len(sm)})

        if parsed.path == '/api/events':
            q = parse_qs(parsed.query)
            limit = int(q.get('limit', ['100'])[0])
            limit = max(1, min(limit, 4000))
            self.store.poll_new()
            events = list(self.store.events)[-limit:]
            events = _with_sensor_mapping(events)
            return self._json({'events': events, 'count': len(self.store.events), 'source': str(self.store.path)})

        if parsed.path == '/api/sensors':
            q = parse_qs(parsed.query)
            source_mode = (q.get('source', ['auto'])[0] or 'auto').strip().lower()
            archive_ids = set(sensor_ids_from_archive()) if source_mode in ('archive', 'combined', 'auto') else set()

            local_ids = set()
            if source_mode in ('local', 'combined', 'auto'):
                self.store.poll_new()
                for ev in list(self.store.events):
                    de = ev.get('decode') or {}
                    sid = de.get('sensor_id')
                    if sid is not None:
                        local_ids.add(str(sid))

            if source_mode == 'archive':
                ids = archive_ids
            elif source_mode == 'local':
                ids = local_ids
            elif source_mode == 'combined':
                ids = local_ids | archive_ids
            else:  # auto
                ids = local_ids | archive_ids
                source_mode = 'auto'

            return self._json({'source_mode': source_mode, 'sensor_ids': sorted(ids)})

        if parsed.path == '/api/views':
            return self._json({'views': load_saved_views()})

        if parsed.path == '/api/trends':
            q = parse_qs(parsed.query)
            sensor_id = (q.get('sensor_id', [''])[0] or '').strip()
            win = q.get('window', ['24h'])[0]
            source_mode = (q.get('source', ['auto'])[0] or 'auto').strip().lower()
            metric = (q.get('metric', ['raw'])[0] or 'raw').strip().lower()
            threshold = q.get('threshold', [None])[0]
            limit = int(q.get('limit', ['2000'])[0])
            limit = max(100, min(limit, 10000))

            # local points
            self.store.poll_new()
            cutoff = time.time() - window_seconds(win)
            local_points = []
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
                    local_points.append({'ts': ts, 'value': float(v)})
            local_points = local_points[-limit:]

            # archive points
            archive_res = {'points': [], 'source': 'archive:none'}
            if source_mode in ('archive', 'combined', 'auto'):
                archive_res = trends_from_archive(sensor_id, win, limit)
            archive_points = archive_res['points']

            if source_mode == 'archive':
                base_points = archive_points
                resolved_source = 'archive'
            elif source_mode == 'local':
                base_points = local_points
                resolved_source = 'local'
            elif source_mode == 'combined':
                base_points = merge_points(local_points, archive_points, limit)
                resolved_source = 'combined'
            else:  # auto
                # prefer local for freshness, backfill from archive when local sparse
                if len(local_points) >= max(20, limit // 10):
                    base_points = local_points
                    resolved_source = 'local'
                else:
                    base_points = merge_points(local_points, archive_points, limit)
                    resolved_source = 'auto'

            points = apply_metric(base_points, metric, threshold)
            vals = [p['value'] for p in points]
            stats = {
                'latest': vals[-1] if vals else None,
                'min': min(vals) if vals else None,
                'max': max(vals) if vals else None,
                'avg': round(sum(vals)/len(vals), 3) if vals else None,
                'local_count': len(local_points),
                'archive_count': len(archive_points),
            }
            return self._json({
                'sensor_id': sensor_id,
                'window': win,
                'source_mode': resolved_source,
                'metric': metric,
                'points': points,
                'stats': stats,
                'source': {'local': str(self.store.path), 'archive': archive_res.get('source', 'archive:none')}
            })

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
                    for ev in _with_sensor_mapping(new_events):
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
