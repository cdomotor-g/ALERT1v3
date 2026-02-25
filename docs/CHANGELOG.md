# Changelog

## Unreleased

### Added
- Issue #5: new MQTT publisher block implementation at `src/ALERT1v3_epy_block_2.py` (incremental, not yet flowgraph-wired).
- Issue #6: decoupled web dashboard backend at `webui/server.py` with REST + SSE endpoints.
- Documentation for new integration paths:
  - `docs/MQTT.md`
  - `docs/WEBUI.md`
- Initial project documentation set:
  - `README.md`
  - `docs/ARCHITECTURE.md`
  - `docs/PROTOCOL.md`
  - `docs/ROADMAP.md`
  - `docs/CHANGELOG.md`

### Changed
- Issue #2: decoder structured event polish in `src/ALERT1v3_epy_block_1.py`:
  - Added explicit `display` field mirroring `summary` for GUI-friendly readability.
  - Kept existing `summary` output stable for operator workflows.
- Issue #4: Qt UI tab layout refined in `src/ALERT1v3.grc`:
  - Introduced explicit tabs: `Operator`, `Signal`, `Diagnostics`.
  - Moved decode message display into Operator view.
  - Shifted symbol/raster internals into Diagnostics view to reduce run-time clutter.
- Issue #3: logger robustness upgrade in `src/ALERT1v3_epy_block_0.py`:
  - Added safe event normalization for malformed/non-dict PMT payloads.
  - Guaranteed fallback schema keys for CSV/JSONL writes.
  - Preserved flush-on-write behavior for both CSV and JSONL sinks.
- Hardened decoder contract in `src/ALERT1v3_epy_block_1.py`:
  - Explicit single-output handling aligned with flowgraph wiring
  - Guarded output writes using scheduler-provided output capacity
  - Added frame collection reset helper for cleaner state transitions
  - Added runtime counters (`frames_decoded`, `frames_dropped_output_full`)
- Synced embedded decoder source in `src/ALERT1v3.grc` with external block file.

### Notes
- Documentation captures current v3 behavior and proposed direction.
- Protocol details remain a working draft pending frame validation.
