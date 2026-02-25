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

## Phase 8 — Next overnight run targets

- [ ] **Finish Issue #5 (MQTT):**
  - wire MQTT block into `src/ALERT1v3.grc`
  - add/verify runtime config vars
  - run end-to-end broker soak validation
- [ ] **Finish Issue #4 (Qt UI):**
  - add Operator-tab counters (decode rate / total / recent errors)
  - tighten layout for faster operator workflow
- [ ] **Add replay fixture/tooling:**
  - one-command replay for decoder → logger → web/MQTT path
  - useful for regression checks and future automation
