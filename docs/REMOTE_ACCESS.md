# Remote access (Tailscale-first)

This runbook secures remote FW-LAB web UI access without exposing port 8088 publicly.

## Current recommended model

- Access via Tailscale only
- UFW allows `8088/tcp` only on `tailscale0`
- Public WAN access to 8088 blocked

## URLs

- `http://100.74.133.62:8088`
- `http://raspberry.taildd3001.ts.net:8088`

## Firewall model

```bash
sudo ufw delete allow 8088/tcp
sudo ufw allow in on tailscale0 to any port 8088 proto tcp comment 'FW-LAB via Tailscale'
```

## Service setup (persistent web UI)

Install unit and enable:

```bash
sudo cp deploy/fwlab-webui.service /etc/systemd/system/fwlab-webui.service
sudo chmod 644 /etc/systemd/system/fwlab-webui.service
sudo chmod +x tools/start_webui.sh
sudo systemctl daemon-reload
sudo systemctl enable --now fwlab-webui.service
sudo systemctl status fwlab-webui.service
```

Logs:

```bash
journalctl -u fwlab-webui.service -f
```

## Rollback

```bash
sudo systemctl disable --now fwlab-webui.service
sudo rm -f /etc/systemd/system/fwlab-webui.service
sudo systemctl daemon-reload
```

Restore LAN/public rule only if intentionally required.
