# Resilience and unattended operation

## Restart policy

Core long-running services are configured with systemd restart behavior:
- `fwlab-receiver.service` (`Restart=always`)
- `fwlab-webui.service` (`Restart=always`)
- `fwlab-host-monitor.service` (`Restart=always`)

Scheduled maintenance and transfer services:
- `fwlab-log-retention.timer` (hourly)
- `fwlab-archive-uploader.timer` (every 10 min)

## Soak evidence

Latest 1-hour soak report:
- `rf_log/soak_20260226_163444/soak_report.json`

Summary from that run:
- decoder events: 1052 (`ok` only)
- estimated decode rate: ~17.8/min
- host metric samples: 720
- host warnings: 16

## Failure modes and operator actions

1) **Receiver online but stale/no data**
- Check `/api/receiver_status` in web UI header state
- Verify SDR access and RF controls
- Run `./tools/fwlabctl restart`

2) **Service crash/restart loops**
- Run `./tools/fwlabctl logs`
- Run `python3 tools/resilience_check.py`
- If repeated restart growth, stop service, inspect last logs, apply config rollback

3) **Low disk pressure**
- Check storage card mode (`warn/critical/emergency`)
- Force cleanup with retention service if needed
- Verify archive uploader timer is active

## Quick health snapshot

```bash
python3 tools/resilience_check.py
```

This reports service active state and restart counters.
