#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime, timezone


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as e:
        return f'ERROR: {e}'


def main():
    out = {
        'schema': 'alert.remote.access.check.v1',
        'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'checks': {},
    }

    ufw = run("sudo ufw status numbered")
    out['checks']['ufw_status'] = ufw
    public_8088 = False
    for line in ufw.splitlines():
        if '8088/tcp' in line and 'Anywhere' in line and 'on tailscale0' not in line:
            public_8088 = True
            break
    out['checks']['public_8088_present'] = public_8088

    ss = run("ss -ltnp | grep ':8088 ' || true")
    out['checks']['web_listen_8088'] = ss

    cfd = run("systemctl is-active cloudflared || true")
    out['checks']['cloudflared_active'] = cfd

    ts = run("tailscale status --json 2>/dev/null || true")
    out['checks']['tailscale_status_json_present'] = ts.startswith('{')

    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
