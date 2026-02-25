# ALERT1v3 Roadmap (Draft)

## Phase 0 — Project Setup (now)

- [x] Create baseline docs
- [ ] Confirm protocol assumptions against sample captures
- [ ] Define schema contract for decoded events (`alert.decode.v1`)

## Phase 1 — Decoder hardening

- [ ] Fix embedded decoder output contract
- [ ] Add status/error paths (framing, timing, invalid fields)
- [ ] Add raw frame capture in decoded output
- [ ] Add reproducible offline decoder test script

## Phase 2 — Logging improvements

- [ ] Keep CSV for simple review
- [ ] Add JSONL structured log sink
- [ ] Add per-day/per-session log organization and retention options

## Phase 3 — UI refinement (Qt)

- [ ] Split UI into:
  - Operate (controls + decoded message feed)
  - Signal (waterfall/time/raster)
  - Diagnostics (decoder internals)
- [ ] Add message counters and recent-error indicators

## Phase 4 — MQTT integration

- [ ] Add MQTT publisher block/module
- [ ] Publish topics:
  - `alert/rx/decoded`
  - `alert/rx/raw`
  - `alert/rx/status`
  - `alert/rx/metrics`
- [ ] Document broker/auth config

## Phase 5 — Web UI MVP

- [ ] Stand up lightweight backend (FastAPI suggested)
- [ ] Serve recent decoded events + live stream
- [ ] Build minimal dashboard (status + table + quick filters)

## Phase 6 — Stabilization

- [ ] Soak tests
- [ ] Performance profiling (CPU/load on Pi)
- [ ] Packaging/run scripts and operator instructions
