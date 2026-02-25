# WORKLOG

## 2026-02-25 22:13:22 AEST — Issue #2
- Status: implemented
- Changes:
  - Added `display` field to `alert.decode.v1` decode events, preserving `summary` compatibility.
  - Updated embedded decoder code in `src/ALERT1v3.grc` to match external block behavior.
  - Updated `docs/PROTOCOL.md` to document the implemented v1 schema keys.
- Validation:
  - `python -m py_compile src/ALERT1v3_epy_block_1.py`
- Commit: `7991ab3`
- Next action: start issue #3 (logger robustness validation + docs).

## 2026-02-25 22:15:00 AEST — Issue #3
- Status: implemented
- Changes:
  - Added `_normalize_event()` in logger to safely handle malformed/non-dict PMT messages.
  - Ensured fallback keys are always present (`schema`, `ts`, `status`, `decode`, `frame`, `summary`, `display`).
  - Synced embedded logger/decoder source in `src/ALERT1v3.grc` from external block files.
- Validation:
  - `python -m py_compile src/ALERT1v3_epy_block_0.py src/ALERT1v3_epy_block_1.py`
- Commit: pending
- Next action: commit/push and update issue #3.
