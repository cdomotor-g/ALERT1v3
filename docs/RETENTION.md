# Log retention and storage controls

FW-LAB includes automated retention to keep disk usage bounded.

## Policy (default)

Configured in `config/storage_policy.json`:

- Local hot retention: **2 days**
- Max local matching logs: **1024 MB**
- Disk thresholds:
  - warn at 85%
  - critical at 92%
  - emergency at 96%

Critical behavior:
- critical mode: tighter retention/size behavior
- emergency mode: most aggressive retention window

Matching files:
- `*.jsonl`
- `*.csv`
- `*.log`

Roots scanned by default:
- `/home/cdomotor/rf_log`
- `/home/cdomotor/.openclaw/workspace/projects/ALERT1v3/rf_log`

## Manual run

```bash
python3 tools/log_retention.py --days 14 --max-mb 1024
python3 tools/log_retention.py --days 14 --max-mb 1024 --dry-run
```

## Service/timer

Installed units:
- `fwlab-log-retention.service`
- `fwlab-log-retention.timer`

Control via:

```bash
./tools/fwlabctl install
./tools/fwlabctl enable
./tools/fwlabctl retention-run
systemctl list-timers fwlab-log-retention.timer
```

## Notes

- Retention is additive safety; keep backups for critical data.
- Current host already trends high on root disk usage, so this should remain enabled.
