# FW-LAB Receiver

**Flood Warning ALERT Base Station Receiver** (short name: **FW-LAB Receiver**) is an RTL-SDR + GNU Radio receiver/decoder flowgraph for ALERT-style transmissions (default center frequency: 173.9 MHz).

Current goals:
- Improve decode clarity and reliability
- Improve operator UX
- Add MQTT integration for downstream systems
- Add a decoupled web UI (without hard dependency on bokehgui)

## Current State

- RF receive via RTL-SDR (`osmosdr`)
- FSK-like demodulation chain + symbol timing recovery
- Hardened embedded protocol decoder with structured status/error taxonomy
- JSONL event logging + CSV data logging
- MQTT event publisher integration
- Web UI suite (`/`, `/events`, `/radio`, `/trends`, `/admin`, `/forensics`, `/about`)
- Systemd-oriented unattended operation on Raspberry Pi

## Quick Start

### A) Recommended (service mode on Pi)

1. Install/start services (see `docs/PACKAGING.md`)
2. Start stack with helper:
   - `./tools/fwlabctl start`
3. Open Web UI (`/`, `/events`, `/radio`)
4. Check health on `/admin` and `/radio`

### B) GNU Radio Companion (interactive)

1. Open `src/ALERT1v3.grc`
2. Confirm SDR and audio devices
3. Start flowgraph
4. Set center frequency / RF gain / RF squelch
5. Monitor decoder output + logs

### C) Cross-host bootstrap installer (new)

```bash
chmod +x scripts/install_fwlab.sh scripts/verify_fwlab.sh
# profile auto-resolves from config/deployment_role.json
./scripts/install_fwlab.sh --profile auto --yes
./scripts/verify_fwlab.sh --profile all
```

Common variants:

```bash
./scripts/install_fwlab.sh --profile webui --yes
./scripts/install_fwlab.sh --profile receiver --user "$USER" --yes
./scripts/install_fwlab.sh --dry-run --profile all
```

Role scaffold lives at `config/deployment_role.json` (`edge`, `control`, or `hybrid/all`).

Quick role switch helper:

```bash
chmod +x scripts/set_role.sh
./scripts/set_role.sh edge --apply --verify
./scripts/set_role.sh control --apply --verify
./scripts/set_role.sh hybrid --apply --verify
```

Control-plane promotion/bootstrap helper:

```bash
chmod +x scripts/promote_control_plane.sh
# Pull latest state from S3, upload this host snapshot, mark active
./scripts/promote_control_plane.sh --pull-first
# Bootstrap only (restore latest state, no promotion)
./scripts/promote_control_plane.sh --bootstrap-only
```

## Web UI Pages

- `/` Dashboard
- `/events` Event table + filters
- `/radio` Live RF health, waveform/waterfall, and browser audio monitor
- `/data` Data explorer (hot+cold query modes; `/trends` alias retained)
- `/path` Path analysis MVP (single-link budget + profile)
- `/stations` Station registry upload/editing
- `/trip` Trip planning with station/address/latlon/map waypoints
- `/admin` Runtime policy/control
- `/forensics` Deep diagnostics page (flowgraph inventory/connectivity + decode review checklist)

`/data` source modes:
- `auto` (default): prefer hot/local when sufficient, backfill with cold/archive when sparse
- `combined`: merge hot + cold with timestamp de-dup
- `local`: hot store only
- `archive`: cold store only
- `/about` About page (renders this README + repo link)

### Browser audio monitor

`/radio` provides in-browser audio monitoring over the same Web UI port (`8088`) via:
- `/api/audio_aac` (best compatibility; preferred on iOS)
- `/api/audio_opus`

Audio controls:
- codec selector (`auto`, `aac`, `opus`)
- gain control
- native HTML audio controls (`playsinline`)

Tip: if mobile appears blocked, use **Load Audio** then press play on the native control.

## Documentation

- Pi-light operations profile: `docs/PI_LIGHT_MODE.md`
- Path analysis API draft: `docs/PATH_ANALYSIS_API.md`

- Architecture: `docs/ARCHITECTURE.md`
- Protocol decode notes: `docs/PROTOCOL.md`
- MQTT integration notes: `docs/MQTT.md`
- Replay/validation fixture: `docs/REPLAY.md`
- Web UI MVP notes: `docs/WEBUI.md`
- Host monitoring (Raspberry Pi): `docs/HOST_MONITORING.md`
- Latest host soak report: `docs/SOAK_REPORT_HOST_MONITOR_2026-02-26.md`
- Sidecar architecture: `docs/SIDECARS.md`
- Platform support matrix: `docs/PLATFORMS.md`
- Remote access runbook: `docs/REMOTE_ACCESS.md`
- Access governance runbook: `docs/REMOTE_ACCESS_ACCESS.md`
- Access model: `docs/ACCESS_MODEL.md`
- Packaging/run mode: `docs/PACKAGING.md`
- Log retention controls: `docs/RETENTION.md`
- Soak and resilience: `docs/SOAK.md`
- Resilience runbook: `docs/RESILIENCE.md`
- Architecture vision: `docs/ARCHITECTURE_VISION.md`
- Components: `docs/COMPONENTS.md`
- Data model/contracts: `docs/DATA_MODEL.md`
- Archive pipeline: `docs/ARCHIVE.md`
- Archive restore validation: `docs/ARCHIVE_RESTORE.md`
- Roadmap and milestones: `docs/ROADMAP.md`
- Versioning + naming policy: `docs/VERSIONING.md`
- Change log: `docs/CHANGELOG.md`

## Forensics / SME verification

Use `/forensics` when you need non-daily deep diagnostics:
- flowgraph block inventory + connectivity extracted from `.grc`
- modulation/decoding narrative and checklist
- exportable SME bundle (`/api/forensics_bundle`) with flowgraph + config + recent events

## Design Direction

Treat GNU Radio as the decode engine, and move integrations/UI to clean interfaces:

- Decoder outputs structured events
- Logger persists CSV + JSONL
- MQTT publishes decoded/status events
- Web UI consumes events from backend service

This separation reduces coupling and avoids repeating UI/tooling dead-ends from previous versions.

## Replay Validation (no SDR required)

Run a full synthetic replay of decoder → logger → MQTT → web API:

```bash
./tools/replay_validate.sh
```

See `docs/REPLAY.md` for details and environment overrides.
