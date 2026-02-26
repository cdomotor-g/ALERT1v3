# Long-run soak and resilience

Use soak runs to validate decoder stability, error behavior, and host resource trend under sustained operation.

## Quick soak

```bash
chmod +x tools/run_soak.sh
./tools/run_soak.sh 600
```

- Argument is duration in seconds (default 3600).
- Output is written to `rf_log/soak_<timestamp>/`.

Artifacts:
- `receiver.log`
- `host_monitor.log`
- `webui.log`
- `rx_events.jsonl`
- `host_metrics.jsonl`
- `soak_report.json`

## Report fields

`soak_report.json` includes:
- total events
- status counts (`ok/warn/error`)
- confidence score stats
- top error codes
- decode rate estimate
- host metrics sample/warn counts

## Resilience notes

- Core services are managed by systemd:
  - `fwlab-webui.service`
  - `fwlab-host-monitor.service`
- Use `./tools/fwlabctl status` and `./tools/fwlabctl logs` during/after soak.
- Keep log retention timer enabled to avoid disk growth issues during extended runs.
