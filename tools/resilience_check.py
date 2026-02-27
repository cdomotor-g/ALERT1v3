#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime, timezone

SERVICES = [
    'fwlab-receiver.service',
    'fwlab-webui.service',
    'fwlab-host-monitor.service',
    'fwlab-archive-uploader.timer',
    'fwlab-log-retention.timer',
]


def systemctl_show(unit):
    keys = [
        'Id', 'ActiveState', 'SubState', 'UnitFileState', 'NRestarts',
        'ExecMainStatus', 'ExecMainCode', 'StateChangeTimestamp',
    ]
    cmd = ['systemctl', 'show', unit, '--no-pager', '--property=' + ','.join(keys)]
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
    data = {}
    for line in out.splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            data[k] = v
    return data


def main():
    report = {
        'schema': 'alert.resilience.check.v1',
        'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'services': {},
        'summary': {'ok': 0, 'warn': 0},
    }

    for s in SERVICES:
        try:
            d = systemctl_show(s)
            active = d.get('ActiveState', 'unknown')
            restarts = int(d.get('NRestarts', '0') or '0')
            status = 'ok' if active == 'active' else 'warn'
            if restarts >= 10:
                status = 'warn'
            d['status'] = status
            report['services'][s] = d
            report['summary'][status] += 1
        except Exception as e:
            report['services'][s] = {'status': 'warn', 'error': str(e)}
            report['summary']['warn'] += 1

    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
