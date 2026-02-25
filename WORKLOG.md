# WORKLOG

## 2026-02-25 22:13:22 AEST — Issue #2
- Status: implemented
- Changes:
  - Added `display` field to `alert.decode.v1` decode events, preserving `summary` compatibility.
  - Updated embedded decoder code in `src/ALERT1v3.grc` to match external block behavior.
  - Updated `docs/PROTOCOL.md` to document the implemented v1 schema keys.
- Validation:
  - `python -m py_compile src/ALERT1v3_epy_block_1.py`
- Commit: pending
- Next action: commit/push and comment/close issue #2.
