#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def iso_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def read_meminfo():
    data = {}
    try:
        with open('/proc/meminfo', 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                parts = line.split(':', 1)
                if len(parts) != 2:
                    continue
                key = parts[0].strip()
                val = parts[1].strip().split()[0]
                data[key] = int(val)
    except Exception:
        return None
    return data


def read_temp_c():
    # Prefer standard thermal zone.
    paths = [
        '/sys/class/thermal/thermal_zone0/temp',
    ]
    for p in paths:
        try:
            raw = Path(p).read_text().strip()
            return float(raw) / 1000.0
        except Exception:
            pass

    # Fallback for Raspberry Pi firmware utility.
    vcg = shutil.which('vcgencmd')
    if vcg:
        try:
            out = subprocess.check_output([vcg, 'measure_temp'], text=True, timeout=2)
            # temp=49.2'C
            if 'temp=' in out:
                v = out.split('temp=', 1)[1].split("'", 1)[0]
                return float(v)
        except Exception:
            pass

    return None


def load_thresholds(args):
    return {
        'cpu_percent': args.warn_cpu,
        'mem_percent': args.warn_mem,
        'disk_percent': args.warn_disk,
        'temp_c': args.warn_temp,
        'load_1m_per_core': args.warn_load,
    }


def compute_breaches(sample, thresholds):
    breaches = []
    checks = {
        'cpu_percent': sample.get('cpu_percent'),
        'mem_percent': sample.get('mem_percent'),
        'disk_percent': sample.get('disk_percent'),
        'temp_c': sample.get('temp_c'),
        'load_1m_per_core': sample.get('load_1m_per_core'),
    }
    for key, value in checks.items():
        limit = thresholds.get(key)
        if value is None or limit is None:
            continue
        if value >= limit:
            breaches.append({'metric': key, 'value': round(float(value), 3), 'threshold': float(limit)})
    return breaches


def maybe_mqtt_client(args):
    if not args.mqtt_host:
        return None
    try:
        import paho.mqtt.client as mqtt
    except Exception as exc:
        print(f'[host-monitor] MQTT disabled (paho-mqtt unavailable): {exc}')
        return None

    client = mqtt.Client(client_id='fw-lab-host-monitor', clean_session=True)
    if args.mqtt_username:
        client.username_pw_set(args.mqtt_username, args.mqtt_password)

    try:
        client.connect(args.mqtt_host, args.mqtt_port, keepalive=30)
        client.loop_start()
    except Exception as exc:
        print(f'[host-monitor] MQTT connect failed: {exc}')
        return None
    return client


def publish_mqtt(client, args, payload):
    if not client:
        return
    topic = f"{args.mqtt_topic_prefix.strip('/')}/rx/host_metrics"
    try:
        client.publish(topic, json.dumps(payload, default=str), qos=0, retain=False)
    except Exception as exc:
        print(f'[host-monitor] MQTT publish failed: {exc}')


def main():
    p = argparse.ArgumentParser(description='FW-LAB host resource monitor (Pi-friendly sidecar).')
    p.add_argument('--interval', type=float, default=5.0, help='Sampling interval seconds')
    p.add_argument('--output-jsonl', default='rf_log/host_metrics.jsonl', help='JSONL output path')

    p.add_argument('--warn-cpu', type=float, default=85.0)
    p.add_argument('--warn-mem', type=float, default=85.0)
    p.add_argument('--warn-disk', type=float, default=90.0)
    p.add_argument('--warn-temp', type=float, default=75.0)
    p.add_argument('--warn-load', type=float, default=1.25, help='1-minute load per core warning threshold')

    p.add_argument('--mqtt-host', default='', help='Optional MQTT host for publishing host metrics')
    p.add_argument('--mqtt-port', type=int, default=1883)
    p.add_argument('--mqtt-username', default='')
    p.add_argument('--mqtt-password', default='')
    p.add_argument('--mqtt-topic-prefix', default='alert')

    args = p.parse_args()

    out = Path(args.output_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    thresholds = load_thresholds(args)
    mqtt_client = maybe_mqtt_client(args)

    prev_cpu = None
    print(f'[host-monitor] writing {out} every {args.interval:.1f}s')

    try:
        while True:
            cpu_percent = None
            with open('/proc/stat', 'r', encoding='utf-8', errors='replace') as f:
                parts = f.readline().split()
                vals = [int(x) for x in parts[1:]]
                idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
                total = sum(vals)
                if prev_cpu:
                    didle = idle - prev_cpu[0]
                    dtotal = total - prev_cpu[1]
                    if dtotal > 0:
                        cpu_percent = 100.0 * (1.0 - (didle / dtotal))
                prev_cpu = (idle, total)

            mem = read_meminfo() or {}
            mem_total = mem.get('MemTotal', 0)
            mem_avail = mem.get('MemAvailable', 0)
            mem_percent = None
            if mem_total > 0:
                mem_percent = 100.0 * (1.0 - (mem_avail / mem_total))

            disk = shutil.disk_usage('/')
            disk_percent = 100.0 * (disk.used / disk.total) if disk.total else None

            load1, load5, load15 = os.getloadavg()
            cores = os.cpu_count() or 1
            load_1m_per_core = load1 / cores if cores else load1

            temp_c = read_temp_c()

            sample = {
                'schema': 'alert.host.metrics.v1',
                'ts': iso_now(),
                'host': {
                    'hostname': os.uname().nodename,
                    'cores': cores,
                },
                'metrics': {
                    'cpu_percent': round(cpu_percent, 3) if cpu_percent is not None else None,
                    'mem_percent': round(mem_percent, 3) if mem_percent is not None else None,
                    'disk_percent': round(disk_percent, 3) if disk_percent is not None else None,
                    'temp_c': round(temp_c, 3) if temp_c is not None else None,
                    'load_1m': round(load1, 3),
                    'load_5m': round(load5, 3),
                    'load_15m': round(load15, 3),
                    'load_1m_per_core': round(load_1m_per_core, 3),
                },
                'thresholds': thresholds,
            }

            flat = {
                'cpu_percent': sample['metrics']['cpu_percent'],
                'mem_percent': sample['metrics']['mem_percent'],
                'disk_percent': sample['metrics']['disk_percent'],
                'temp_c': sample['metrics']['temp_c'],
                'load_1m_per_core': sample['metrics']['load_1m_per_core'],
            }
            breaches = compute_breaches(flat, thresholds)
            sample['breaches'] = breaches
            sample['status'] = 'warn' if breaches else 'ok'

            with out.open('a', encoding='utf-8') as f:
                f.write(json.dumps(sample, default=str) + '\n')

            publish_mqtt(mqtt_client, args, sample)
            time.sleep(max(0.5, args.interval))
    except KeyboardInterrupt:
        pass
    finally:
        if mqtt_client:
            try:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
            except Exception:
                pass


if __name__ == '__main__':
    main()
