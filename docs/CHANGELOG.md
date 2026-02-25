# Changelog

## Unreleased

### Added
- Initial project documentation set:
  - `README.md`
  - `docs/ARCHITECTURE.md`
  - `docs/PROTOCOL.md`
  - `docs/ROADMAP.md`
  - `docs/CHANGELOG.md`

### Changed
- Hardened decoder contract in `src/ALERT1v3_epy_block_1.py`:
  - Explicit single-output handling aligned with flowgraph wiring
  - Guarded output writes using scheduler-provided output capacity
  - Added frame collection reset helper for cleaner state transitions
  - Added runtime counters (`frames_decoded`, `frames_dropped_output_full`)
- Synced embedded decoder source in `src/ALERT1v3.grc` with external block file.

### Notes
- Documentation captures current v3 behavior and proposed direction.
- Protocol details remain a working draft pending frame validation.
