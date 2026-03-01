# ALERT Roadmap

## Phase 0 — Project setup

- [x] Create baseline docs
- [ ] Confirm protocol assumptions against sample captures
- [x] Define schema contract for decoded events (`alert.decode.v1`)

## Phase 1 — Decoder hardening

- [x] Fix embedded decoder output contract
- [ ] Add status/error paths (framing, timing, invalid fields)
- [x] Add raw frame capture in decoded output
- [ ] Add reproducible offline decoder test script

## Phase 2 — Logging improvements

- [x] Keep CSV for simple review
- [x] Add JSONL structured log sink
- [ ] Add per-day/per-session log organization and retention options

## Phase 3 — UI refinement (Qt)

- [x] Split UI into:
  - Operator (controls + decoded message feed)
  - Signal (waterfall/time/raster)
  - Diagnostics (decoder internals)
- [ ] Add message counters and recent-error indicators

## Phase 4 — MQTT integration

- [x] Add MQTT publisher block/module
- [x] Document broker/auth config
- [ ] Wire MQTT block into main `.grc` flowgraph by default
- [ ] Validate publish topics live with broker soak test:
  - `alert/rx/decoded`
  - `alert/rx/raw`
  - `alert/rx/status`
  - `alert/rx/metrics`

## Phase 5 — Web UI MVP

- [x] Stand up lightweight backend
- [x] Serve recent decoded events + live stream
- [x] Build minimal dashboard (status + table + quick filters)

## Phase 6 — Stabilization

- [ ] Soak tests
- [ ] Performance profiling (CPU/load on Pi)
- [ ] Packaging/run scripts and operator instructions

## Phase 7 — ALERT2 capability

- [ ] Define ALERT2 scope and compatibility goals
- [ ] Document protocol/interface differences vs ALERT
- [ ] Add decoder extension plan (feature flags or parallel decode path)
- [ ] Add test captures/replay cases for ALERT2

## Phase 7.1 — IFLOWS / Enhanced IFLOWS (EIF) planning (no implementation yet)

- [ ] Add EIF protocol appendix to docs (layout, marker bits, CRC-6 polynomial)
- [ ] Define dual-format compatibility plan: ALERT Binary + EIF coexistence in decoder pipeline
- [ ] Specify EIF decode contract fields in `alert.decode.v1` (format family, crc_ok, raw bytes)
- [ ] Define configurable CRC-6 parameters for field validation (`init`, reflection, xor, bit-order)
- [ ] Capture at least one known-good real EIF sample to lock CRC behavior for this network
- [ ] Add replay fixtures + acceptance tests for EIF once sample truth data is available
- [ ] Decide rollout strategy (feature flag / passive detect / strict mode) and operator controls

## Phase 8 — Operational completion targets

- [x] Finish Raspberry Pi host monitoring acceptance (breach surfacing + soak summary + helper runner)
- [x] Complete log retention/rotation controls
- [x] Package one-command run mode for unattended deployments

## Phase 9 — Multi-platform and sidecar architecture

- [x] Define platform matrix (Raspberry Pi / Linux x86_64 / macOS / Windows where feasible)
- [x] Introduce sidecar interface contracts (monitoring, replay, integration bridges)
- [x] Refactor host monitor into a platform-adapter model
- [x] Add naming/structure conventions for cross-platform sidecars
- [ ] Add CI smoke checks for key platform paths

## Phase 10 — RF web observability expansion (later)

- [ ] Add richer RF telemetry panel (signal power/noise/lock quality)
- [ ] Add PSD/spectrum mini-view updates for web UI
- [ ] Design full web equivalents for waterfall/time sinks
- [ ] Evaluate transport/performance budget for real-time sink streaming
- [ ] Add remote RF control safety model (authz + audit trail)
