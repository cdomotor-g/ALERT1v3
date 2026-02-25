#!/usr/bin/env python3
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from adapters.linux_proc import LinuxProcAdapter


def iso_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def compute_breaches(metrics, thresholds):
    breaches = []
    for key, limit in thresholds.items():
        value = metrics.get(key)
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
    prefix = args.mqtt_topic_prefix.strip('/')
    topic = f"{prefix}/rx/host_metrics"
    try:
        client.publish(topic, json.dumps(payload, default=str), qos=0, retain=False)
        if payload.get('status') == 'warn':
            status_payload = {
                'schema': 'alert.host.status.v1',
                'ts': payload.get('ts'),
                'status': 'warn',
                'source': 'host_monitor',
                'breaches': payload.get('breaches', []),
            }
            client.publish(f"{prefix}/rx/status", json.dumps(status_payload, default=str), qos=0, retain=False)
    except Exception as exc:
        print(f'[host-monitor] MQTT publish failed: {exc}')


def build_thresholds(args):
    return {
        'cpu_percent': args.warn_cpu,
        'mem_percent': args.warn_mem,
        'disk_percent': args.warn_disk,
        'temp_c': args.warn_temp,
        'load_1m_per_core': args.warn_load,
    }


def build_arg_parser():
    p = argparse.ArgumentParser(description='FW-LAB host resource monitor sidecar.')
    p.add_argument('--platform', default='linux', choices=['linux'])
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
    return p


def main():
    args = build_arg_parser().parse_args()

    out = Path(args.output_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    thresholds = build_thresholds(args)
    mqtt_client = maybe_mqtt_client(args)

    if args.platform == 'linux':
        adapter = LinuxProcAdapter()
    else:
        raise SystemExit(f'Unsupported platform adapter: {args.platform}')

    print(f'[host-monitor] adapter={adapter.name} writing {out} every {args.interval:.1f}s')

    try:
        while True:
            sample = {
                'schema': 'alert.host.metrics.v1',
                'ts': iso_now(),
                'thresholds': thresholds,
            }
            sample.update(adapter.sample())

            breaches = compute_breaches(sample['metrics'], thresholds)
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
