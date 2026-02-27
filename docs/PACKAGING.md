# Packaging and one-command run mode

FW-LAB provides `fwlabctl` for service-based operation.

## One-command setup

From repo root:

```bash
chmod +x tools/fwlabctl
./tools/fwlabctl install
./tools/fwlabctl enable
```

This installs and enables:
- `fwlab-webui.service`
- `fwlab-host-monitor.service`
- `fwlab-log-retention.timer` (daily cleanup)
- `fwlab-archive-uploader.timer` (10-min archive upload run)

## Operations

```bash
./tools/fwlabctl status
./tools/fwlabctl restart
./tools/fwlabctl stop
./tools/fwlabctl logs
./tools/fwlabctl retention-run
./tools/fwlabctl archive-run
```

## Environment overrides

The helper start scripts support environment variables:

- `tools/start_webui.sh`: chooses latest `rx_events_*.jsonl`
- `tools/start_host_monitor.sh`:
  - `LOG_BASE`
  - `HOST_METRICS_JSONL`
  - `MON_INTERVAL`
  - `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS`, `MQTT_PREFIX`

For persistent overrides, create systemd drop-ins:

```bash
sudo systemctl edit fwlab-host-monitor.service
```

## Rollback

```bash
./tools/fwlabctl disable
sudo rm -f /etc/systemd/system/fwlab-webui.service /etc/systemd/system/fwlab-host-monitor.service
sudo systemctl daemon-reload
```
