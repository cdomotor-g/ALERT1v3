# ALERT1v3

ALERT1v3 is an RTL-SDR + GNU Radio receiver/decoder flowgraph for legacy ALERT-style transmissions (default center frequency: 173.9 MHz).

Current goals:
- Improve decode clarity and reliability
- Improve operator UX
- Add MQTT integration for downstream systems
- Add a decoupled web UI (without hard dependency on bokehgui)

## Current State (v3 baseline)

- RF receive via RTL-SDR (`osmosdr`)
- FSK-like demodulation chain and symbol sync
- Custom embedded protocol decoder block
- GUI with tuning controls, waterfalls, time/raster views
- CSV logger for decoded message/debug payloads

## Quick Start (current flowgraph)

1. Open `ALERT1v3.grc` in GNU Radio Companion
2. Confirm SDR and audio devices are available
3. Start flowgraph
4. Set:
   - Center frequency
   - RF gain
   - RF squelch
5. Monitor decoded output and logs

## Documentation

- Architecture: `docs/ARCHITECTURE.md`
- Protocol decode notes: `docs/PROTOCOL.md`
- MQTT integration notes: `docs/MQTT.md`
- Replay/validation fixture: `docs/REPLAY.md`
- Web UI MVP notes: `docs/WEBUI.md`
- Roadmap and milestones: `docs/ROADMAP.md`
- Change log: `docs/CHANGELOG.md`

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
