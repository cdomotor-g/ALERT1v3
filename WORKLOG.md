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
- Commit: `6a999c5`
- Next action: begin issue #4 (tab/layout refinement).

## 2026-02-25 22:18:44 AEST — Issue #4
- Status: partial
- Changes:
  - Updated Qt tab model to `Operator`, `Signal`, `Diagnostics` in `src/ALERT1v3.grc`.
  - Moved decoded message widget to Operator tab.
  - Moved symbol/raster internals into Diagnostics tab.
- Validation:
  - `python -m py_compile src/ALERT1v3_epy_block_0.py src/ALERT1v3_epy_block_1.py`
- Commit: `3146e6e`
- Next action: implement issue #5 increment (MQTT publisher module + docs).

## 2026-02-25 22:18:44 AEST — Issue #5
- Status: partial
- Changes:
  - Added MQTT publisher implementation `src/ALERT1v3_epy_block_2.py`.
  - Implemented topic outputs: `rx/decoded`, `rx/raw`, `rx/status`, `rx/metrics` under configurable prefix.
  - Added `docs/MQTT.md` for broker/auth/topic details.
- Validation:
  - `python -m py_compile src/ALERT1v3_epy_block_2.py`
- Commit: `0329a6e`
- Next action: implement issue #6 (decoupled web UI backend + dashboard).

## 2026-02-25 22:18:44 AEST — Issue #6
- Status: implemented
- Changes:
  - Added decoupled backend/dashboard `webui/server.py` with:
    - REST endpoint (`/api/events`)
    - Live stream endpoint (`/api/live`, SSE)
    - Browser dashboard (`/`) with status + recent table + filter
  - Added usage docs in `docs/WEBUI.md` and linked docs from `README.md`.
- Validation:
  - `python -m py_compile webui/server.py`
- Commit: `566aa74`
- Next action: update issue threads with acceptance/partial status and close where complete.

## 2026-02-25 22:46:26 AEST — Issue #4 + #5 completion
- Status: implemented
- Changes:
  - Wired MQTT publisher into default flowgraph (`src/ALERT1v3.grc` + regenerated `src/ALERT1v3.py`).
  - Added runtime variables in flowgraph: `mqtt_broker_host`, `mqtt_broker_port`, `mqtt_username`, `mqtt_password`, `mqtt_topic_prefix`, `log_base_path`.
  - Connected decoder `debug_out` -> logger + MQTT publisher.
  - Added Operator tab counter display (`Decoder counters`) fed from new decoder `stats_out` message port.
  - Upgraded decoder internals to emit live operator stats (decode rate / total / recent errors).
  - Fixed decoder frame reset logic so full 4-word frames decode correctly (unblocked replay + live validation).
- Validation:
  - `grcc src/ALERT1v3.grc -o src`
  - `python3 -m py_compile src/ALERT1v3.py src/ALERT1v3_epy_block_0.py src/ALERT1v3_epy_block_1.py src/ALERT1v3_epy_block_2.py`
- Commit: `b75b2ca`
- Next action: add one-command replay fixture/tooling + docs + full chain validation output capture.
