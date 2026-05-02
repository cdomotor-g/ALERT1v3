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
from webui.routes_control import handle_control_get

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
NAV_HTML = Path('webui/templates/nav_shell.html').read_text(encoding='utf-8', errors='replace').format(BUILD_STAMP=BUILD_STAMP)



HTML = Path('webui/templates/packets.html').read_text(encoding='utf-8', errors='replace')



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


PATH_HTML = Path('webui/templates/path.html').read_text(encoding='utf-8', errors='replace')


STATIONS_HTML = Path('webui/templates/stations.html').read_text(encoding='utf-8', errors='replace')


STATIONS_MAP_HTML = Path('webui/templates/stations_map.html').read_text(encoding='utf-8', errors='replace')


TRIP_HTML = Path('webui/templates/trip.html').read_text(encoding='utf-8', errors='replace')


FILE_DROP_HTML = Path('webui/templates/file_drop.html').read_text(encoding='utf-8', errors='replace')


BITFLIPPER_HTML = Path('webui/templates/bitflipper.html').read_text(encoding='utf-8', errors='replace')


CONTROL_HTML = Path('webui/templates/control.html').read_text(encoding='utf-8', errors='replace')


OVERVIEW_HTML = Path('webui/templates/overview.html').read_text(encoding='utf-8', errors='replace')


HELP_HTML = Path('webui/templates/help.html').read_text(encoding='utf-8', errors='replace')

ADMIN_HTML = Path('webui/templates/admin.html').read_text(encoding='utf-8', errors='replace')



TRENDS_HTML = Path('webui/templates/trends.html').read_text(encoding='utf-8', errors='replace')


RADIO_HTML = Path('webui/templates/radio.html').read_text(encoding='utf-8', errors='replace')


FORENSICS_HTML = Path('webui/templates/forensics.html').read_text(encoding='utf-8', errors='replace')




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


def _load_control_endpoints(path='config/control_plane_endpoints.json'):
    p = Path(path)
    dflt = {
        'schema': 'fwlab.control_endpoints.v1',
        'activeBaseUrl': '',
        'ingestPath': '/api/control/ingest',
        'statusPath': '/api/control/policy',
        'candidates': {},
    }
    if not p.exists():
        return dflt
    try:
        d = json.loads(p.read_text(encoding='utf-8', errors='replace'))
        if not isinstance(d, dict):
            return dflt
        out = dict(dflt)
        out.update(d)
        return out
    except Exception:
        return dflt


def _control_state_summary():
    out = {
        'role': load_deployment_role().get('role', 'edge'),
        'local_active_base_url': _load_control_endpoints().get('activeBaseUrl', ''),
        's3_active_control_plane': {},
        's3_active_endpoint': {},
    }
    try:
        policy = json.loads(Path('config/archive_policy.json').read_text(encoding='utf-8', errors='replace'))
        role = load_deployment_role()
        prefix = str(((role.get('control') or {}).get('state_prefix') or 'fwlab/control-plane')).strip('/ ')
        bucket = str(policy.get('bucket', '')).strip()
        if not bucket:
            return out
        envp = Path('config/archive_env')
        if envp.exists():
            for ln in envp.read_text(encoding='utf-8', errors='replace').splitlines():
                if '=' in ln and not ln.strip().startswith('#'):
                    k,v=ln.split('=',1)
                    os.environ.setdefault(k.strip(), v.strip())
        if 'AWS_ACCESS_KEY_ID' not in os.environ or 'AWS_SECRET_ACCESS_KEY' not in os.environ:
            return out
        try:
            import boto3  # type: ignore
        except Exception:
            return out
        session = boto3.session.Session(
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
        )
        s3 = session.client('s3', endpoint_url=policy.get('endpoint') or None, region_name=policy.get('region') or None)
        def _get_json(key):
            try:
                obj = s3.get_object(Bucket=bucket, Key=key)
                return json.loads(obj['Body'].read().decode('utf-8', errors='replace'))
            except Exception:
                return {}
        out['s3_active_control_plane'] = _get_json(f'{prefix}/active_control_plane.json')
        out['s3_active_endpoint'] = _get_json(f'{prefix}/active_endpoint.json')
    except Exception:
        pass
    return out


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

    # thin wrappers used by extracted route helpers
    def load_control_plane_policy(self):
        return load_control_plane_policy()

    def _control_state_summary(self):
        return _control_state_summary()

    def _control_ingest_paths(self):
        return _control_ingest_paths()

    def _is_valid_rxs_id(self, v):
        return _is_valid_rxs_id(v)

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

        if parsed.path == '/api/receivers_registry_update':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                raw = self.rfile.read(length) if length > 0 else b'{}'
                body = json.loads(raw.decode('utf-8', errors='replace'))
                op = str(body.get('op', 'upsert')).strip().lower()  # upsert|delete
                item = body.get('item', {}) or {}
                rxs_id = str(item.get('rxs_id', body.get('rxs_id', ''))).strip().upper()
                if not _is_valid_rxs_id(rxs_id):
                    return self._json({'ok': False, 'error': 'invalid_rxs_id'}, code=400)
                reg = _load_receivers_registry()
                rows = reg.get('receivers', []) or []
                idx = next((i for i, r in enumerate(rows) if str(r.get('rxs_id', '')).strip().upper() == rxs_id), -1)
                if op == 'delete':
                    if idx >= 0:
                        rows.pop(idx)
                    reg['receivers'] = rows
                    RECEIVERS_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
                    RECEIVERS_REGISTRY_PATH.write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
                    return self._json({'ok': True, 'op': 'delete', 'rxs_id': rxs_id})

                # upsert
                rec = {
                    'rxs_id': rxs_id,
                    'name': str(item.get('name', '')).strip() or f'RX {rxs_id}',
                    'location': str(item.get('location', '')).strip(),
                    'base_url': str(item.get('base_url', 'local')).strip() or 'local',
                    'status': str(item.get('status', '')).strip(),
                }
                if idx >= 0:
                    rows[idx].update(rec)
                else:
                    rows.append(rec)
                reg['receivers'] = rows
                RECEIVERS_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
                RECEIVERS_REGISTRY_PATH.write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
                return self._json({'ok': True, 'op': 'upsert', 'rxs_id': rxs_id})
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
            '/', '/dashboard', '/events', '/packets', '/overview', '/help', '/control', '/trends', '/data', '/path', '/stations', '/stations-map', '/map',
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
        if parsed.path.startswith('/static/'):
            rel = parsed.path[len('/static/'):]
            fp = Path('webui/static') / rel
            if not fp.exists() or not fp.is_file():
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return
            ctype = 'application/javascript; charset=utf-8' if fp.suffix.lower() == '.js' else 'text/plain; charset=utf-8'
            raw = fp.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        _ctl = handle_control_get(self, parsed)
        if _ctl is not None:
            return

        if parsed.path == '/':
            self.send_response(HTTPStatus.FOUND)
            self.send_header('Location', '/stations-map')
            self.end_headers()
            return

        if parsed.path == '/dashboard':
            payload = HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path in ['/events', '/packets']:
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

        if parsed.path == '/control':
            payload = CONTROL_HTML.replace('__NAV__', NAV_HTML).encode('utf-8')
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

        if parsed.path == '/api/control/state_summary':
            return self._json(_control_state_summary())

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
