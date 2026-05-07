# Wiring & Pinout Library

This folder is the canonical source for wiring references.

## Design Goals
- Keep data structured (machine-readable) so it can drive UI later.
- Keep diagrams printable (markdown + simple ASCII where possible).
- Track revision history in git.

## Layout
- `pinouts/` → connector-level references (e.g., DB9 pin maps)
- `cables/` → cable wiring maps (e.g., null modem variants)
- `systems/` → higher-level system wiring diagrams (future)

## Data Model (v1)
Each connector/cable should include:
- `id` (stable key)
- `name`
- `orientation_notes`
- `pins` or `wires`
- `notes`
- `source` / provenance

This v1 starter focuses on DB9 plugs/cables and null modem basics.
