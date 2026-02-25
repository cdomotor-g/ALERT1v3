# Versioning and naming policy

## Product name

Use **Flood Warning ALERT Base Station Receiver** as the formal name.

Use **FW-LAB Receiver** as the short name.

Do not use `v3` suffixes in user-facing naming.

## Version line

Use semantic release labels moving forward:
- current planning line: **v0.2**
- future: **v0.3**, **v1.0**, etc.

## Why files still contain `ALERT1v3`

Some runtime files still include `ALERT1v3` in filenames and class IDs (e.g. `src/ALERT1v3.grc`, `ALERT1v3.py`, embedded block module names).

This is currently intentional for compatibility while we stabilize features.

## Planned cleanup

A dedicated refactor will rename internal artifacts to neutral names (e.g. `ALERT.grc`, `alert_epy_block_*`) once compatibility risks are lower.

Until then:
- docs and roadmap use **ALERT** and semantic milestones,
- code references may still include `ALERT1v3`.
