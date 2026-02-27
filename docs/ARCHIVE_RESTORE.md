# Archive Restore Validation Runbook

This runbook validates that archive chunk artifacts can be read and trusted locally before/after DCS upload workflows.

## Tool

- `tools/archive_restore_check.py`

Checks performed per manifest entry:
- chunk file exists
- gzip stream is readable
- SHA256 matches manifest (when present)
- event count matches manifest (when present)
- first/last timestamp match manifest (when present)

## Run examples

```bash
python3 tools/archive_restore_check.py --manifest rf_log/archive_state/manifest.json --limit 20
python3 tools/archive_restore_check.py --manifest rf_log/archive_state/manifest.json --limit 100 --out rf_log/archive_state/restore_check_latest.json
```

## Interpreting results

- `ok == checked`: restore path integrity checks passed for selected sample.
- any `failed > 0`: inspect `results[]` entries and repair/regenerate affected chunks.

## Operational guidance

- Run restore checks after major uploader changes.
- Run restore checks periodically (e.g. daily/weekly via timer) for confidence.
- Keep manifest and chunk directories under retention/backup policy.

## Incident response

If a chunk fails validation:
1. mark chunk entry as `failed` in manifest (or move out of pending flow)
2. re-chunk source file if still available
3. re-upload and re-run restore validation
