#!/usr/bin/env python3
import argparse
import importlib
import json
import platform
import shutil
import sys


def has_module(name):
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description='FW-LAB platform capability probe')
    ap.add_argument('--json', action='store_true', help='Emit JSON only')
    args = ap.parse_args()

    caps = {
        'schema': 'alert.platform.capabilities.v1',
        'python': sys.version.split()[0],
        'platform': {
            'system': platform.system(),
            'release': platform.release(),
            'machine': platform.machine(),
        },
        'commands': {
            'python3': bool(shutil.which('python3')),
            'mosquitto': bool(shutil.which('mosquitto')),
            'mosquitto_sub': bool(shutil.which('mosquitto_sub')),
            'curl': bool(shutil.which('curl')),
        },
        'python_modules': {
            'pmt': has_module('pmt'),
            'gnuradio': has_module('gnuradio'),
            'paho.mqtt.client': has_module('paho.mqtt.client'),
        },
    }

    caps['workloads'] = {
        'web_ui': caps['commands']['python3'],
        'mqtt_tools': caps['commands']['mosquitto'] and caps['commands']['mosquitto_sub'],
        'perf_sidecar_linux': caps['platform']['system'] == 'Linux',
        'gnu_radio_decode': caps['python_modules']['gnuradio'] and caps['python_modules']['pmt'],
    }

    if args.json:
        print(json.dumps(caps))
    else:
        print(json.dumps(caps, indent=2))


if __name__ == '__main__':
    main()
