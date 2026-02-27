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
- compression to chunk artifacts (`.jsonl.gz`) in state dir
- manifest tracking for pending upload entries

### Run

```bash
python3 tools/archive_uploader.py --dry-run
python3 tools/archive_uploader.py
```

Manifest output:
- `<stateDir>/manifest.json`

## Next steps

- add S3-compatible upload execution (R2/B2/S3)
- add retry loop and backoff state transitions
- add restore/integrity validation tooling

## Security notes

- Do not commit access keys into repo.
- Use environment variables or host secret store.
- Restrict bucket policy to required prefix/actions.
