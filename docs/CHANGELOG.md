# Changelog

## Unreleased

### Added
- Raspberry Pi host monitoring sidecar: `tools/host_monitor.py` (JSONL + optional MQTT publish).
- Host metrics docs: `docs/HOST_MONITORING.md`.

### Changed
- Web dashboard (`webui/server.py`) now supports optional host metrics input via `--host-metrics-jsonl` and `/api/host_metrics`.

### Added
- Issue #5: MQTT publisher block wired by default in `src/ALERT1v3.grc`/`src/ALERT1v3.py` with runtime vars (`mqtt_broker_host`, `mqtt_broker_port`, `mqtt_username`, `mqtt_password`, `mqtt_topic_prefix`).
- Issue #4: Operator-tab decode counters (`decode rate`, `total decodes`, `recent errors`) via `stats_out` + `Decoder counters` widget.
- Replay fixture/tooling:
  - `tools/replay_pipeline.py`
  - `tools/replay_validate.sh`
  - `docs/REPLAY.md`
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
  - Fixed frame/word reset behavior so full 4-word frames decode correctly
  - Added runtime counters (`frames_decoded`, `frames_dropped_output_full`) and operator stats output (`stats_out`)
- Synced embedded decoder source in `src/ALERT1v3.grc` with external block file.

### Notes
- Documentation captures current v3 behavior and proposed direction.
- Protocol details remain a working draft pending frame validation.
