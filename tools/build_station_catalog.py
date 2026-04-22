#!/usr/bin/env python3
import csv, json, re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE_STATIONS = ROOT / 'config/stations.csv'
SENSOR_MAP = ROOT / 'uploads/file_drop/z_Sensors_with_Database_IDs_by_View.csv'
KML_PATH = ROOT / 'uploads/file_drop/myplaces.kml'
OUT_CSV = ROOT / 'config/stations_catalog.csv'
OUT_META = ROOT / 'config/station_metadata.json'


def norm(s: str) -> str:
    s = (s or '').strip().lower()
    s = re.sub(r'\balert\b', 'al', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def load_base():
    rows = []
    if not BASE_STATIONS.exists():
        return rows
    with BASE_STATIONS.open('r', encoding='utf-8', errors='replace', newline='') as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            rows.append({(k or '').strip().lower(): (v or '').strip() for k, v in r.items()})
    return rows


def load_sensor_map():
    sensors_by_bom = {}
    if not SENSOR_MAP.exists():
        return sensors_by_bom
    with SENSOR_MAP.open('r', encoding='utf-8', errors='replace', newline='') as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            site = (r.get('Site') or '').strip()
            bom = (r.get('Site ID') or '').strip()
            sensor = (r.get('Sensor') or '').strip()
            sensor_id = (r.get('Sensor ID') or '').strip()
            arro_site = (r.get('site_id') or '').strip()
            device_id = (r.get('device_id') or '').strip()
            if not bom:
                continue
            d = sensors_by_bom.setdefault(bom, {'site': site, 'arro_site_id': arro_site, 'sensors': set(), 'sensor_ids': set(), 'device_ids': set()})
            if sensor:
                d['sensors'].add(sensor)
            if sensor_id:
                d['sensor_ids'].add(sensor_id)
            if device_id:
                d['device_ids'].add(device_id)
    return sensors_by_bom


def load_kml():
    by_name = {}
    if not KML_PATH.exists():
        return by_name
    ns = {'k': 'http://www.opengis.net/kml/2.2'}
    root = ET.parse(KML_PATH).getroot()
    for pm in root.findall('.//k:Placemark', ns):
        name = (pm.findtext('k:name', default='', namespaces=ns) or '').strip()
        coord = (pm.findtext('.//k:Point/k:coordinates', default='', namespaces=ns) or '').strip()
        if not name or not coord:
            continue
        lon = lat = elev = ''
        try:
            parts = coord.split(',')
            lon = parts[0].strip()
            lat = parts[1].strip() if len(parts) > 1 else ''
            elev = parts[2].strip() if len(parts) > 2 else ''
        except Exception:
            pass
        by_name[norm(name)] = {'kml_name': name, 'latitude': lat, 'longitude': lon, 'elevation': elev}
    return by_name


def main():
    base = load_base()
    sb = load_sensor_map()
    kml = load_kml()

    out = []
    seen = set()

    for r in base:
        uid = (r.get('unitid') or '').strip()
        name = (r.get('unitname') or '').strip()
        key = uid or norm(name)
        seen.add(key)

        sm = sb.get(uid, {})
        site_name = (sm.get('site') or name or '').strip()
        km = kml.get(norm(site_name)) or kml.get(norm(name)) or {}

        row = {
            'unitid': uid,
            'unitname': site_name or name,
            'enabled': r.get('enabled', ''),
            'latitude': r.get('latitude') or km.get('latitude', ''),
            'longitude': r.get('longitude') or km.get('longitude', ''),
            'elevation': r.get('elevation') or km.get('elevation', ''),
            'site_id_bom': uid,
            'arro_site_id': sm.get('arro_site_id', ''),
            'sensor_types': ', '.join(sorted(sm.get('sensors', set()))),
            'sensor_ids': ', '.join(sorted(sm.get('sensor_ids', set()))),
            'device_ids': ', '.join(sorted(sm.get('device_ids', set()))),
            'kml_name': km.get('kml_name', ''),
            'source': 'base+sensor_map+kml' if sm and km else ('base+sensor_map' if sm else ('base+kml' if km else 'base')),
        }
        out.append(row)

    # sensor-map sites missing in base
    for bom, sm in sb.items():
        if bom in seen:
            continue
        site = sm.get('site', '')
        km = kml.get(norm(site), {})
        out.append({
            'unitid': bom,
            'unitname': site,
            'enabled': '1',
            'latitude': km.get('latitude', ''),
            'longitude': km.get('longitude', ''),
            'elevation': km.get('elevation', ''),
            'site_id_bom': bom,
            'arro_site_id': sm.get('arro_site_id', ''),
            'sensor_types': ', '.join(sorted(sm.get('sensors', set()))),
            'sensor_ids': ', '.join(sorted(sm.get('sensor_ids', set()))),
            'device_ids': ', '.join(sorted(sm.get('device_ids', set()))),
            'kml_name': km.get('kml_name', ''),
            'source': 'sensor_map+kml' if km else 'sensor_map',
        })
        seen.add(bom)

    # kml-only sites
    existing_name_norms = {norm(r.get('unitname', '')) for r in out}
    for nk, km in kml.items():
        if nk in existing_name_norms:
            continue
        out.append({
            'unitid': '',
            'unitname': km.get('kml_name', ''),
            'enabled': '',
            'latitude': km.get('latitude', ''),
            'longitude': km.get('longitude', ''),
            'elevation': km.get('elevation', ''),
            'site_id_bom': '',
            'arro_site_id': '',
            'sensor_types': '',
            'sensor_ids': '',
            'device_ids': '',
            'kml_name': km.get('kml_name', ''),
            'source': 'kml',
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ['unitid', 'unitname', 'enabled', 'latitude', 'longitude', 'elevation', 'site_id_bom', 'arro_site_id', 'sensor_types', 'sensor_ids', 'device_ids', 'kml_name', 'source']
    with OUT_CSV.open('w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, '') for k in fields})

    meta = {
        'base_rows': len(base),
        'sensor_map_sites': len(sb),
        'kml_points': len(kml),
        'catalog_rows': len(out),
        'outputs': {'csv': str(OUT_CSV), 'meta': str(OUT_META)}
    }
    OUT_META.write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
