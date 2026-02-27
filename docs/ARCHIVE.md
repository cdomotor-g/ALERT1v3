# Archive (DCS) Pipeline

This document defines the initial S3-compatible archival workflow for long-term storage.

## Configuration

Policy file:
- `config/archive_policy.json`

Key fields:
- endpoint/region/bucket/prefix
- chunking/compression controls
- retry/backoff controls
- sourceRoots
- stateDir

## Scaffold tool

`tools/archive_uploader.py` currently provides:
- discovery of new `rx_events_*.jsonl`
- chunked compression to upload artifacts (`.jsonl.gz`) using policy limits
- manifest tracking for pending upload entries
- processed source file tracking via `source_state.json`

### Run

```bash
python3 tools/archive_uploader.py --dry-run   # planning only, no state mutation
python3 tools/archive_uploader.py             # create chunks + update manifest/state
```

State outputs:
- `<stateDir>/manifest.json`
- `<stateDir>/source_state.json`

## Upload worker behavior

When `enabled=true` and bucket settings are configured, uploader attempts to send pending chunks to S3-compatible storage.

Manifest status flow:
- `pending` -> `uploaded` (success)
- `pending` -> `failed` (error, increments `retry_count`)

Retry model:
- retries are bounded by `upload.maxRetries`
- failed entries are retried in later runs until cap reached

## Credentials

Use environment-based credentials (do not commit secrets):
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- optional: `AWS_SESSION_TOKEN`

Service mode uses:
- `config/archive_env` (see `config/archive_env.example`)

Copy and edit:

```bash
cp config/archive_env.example config/archive_env
# set real credentials
chmod 600 config/archive_env
```

## Restore/integrity validation

- Use `tools/archive_restore_check.py` to verify chunk integrity against manifest metadata.
- Runbook: `docs/ARCHIVE_RESTORE.md`.

## Next steps

- add explicit backoff scheduling metadata and jitter
- wire optional scheduled restore-check jobs

## Security notes

- Do not commit access keys into repo.
- Use environment variables or host secret store.
- Restrict bucket policy to required prefix/actions.
