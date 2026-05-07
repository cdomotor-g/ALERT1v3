# FW-LAB Roadmap Epics

This roadmap captures medium/long-horizon product capabilities beyond current refactor/tuning work.

## EPIC 1 — Mobile App Delivery (iOS + Android)

**Goal:** Deliver a mobile app experience without fragmenting the codebase.

### Scope
- Reuse existing web UI/API where possible.
- Evaluate wrapper-first strategy (PWA / Capacitor / React Native WebView) before native-heavy rewrites.
- Support login/session, station views, packets, key tools, and control pages in mobile layouts.

### Milestones
1. Mobile architecture decision record (ADR): PWA vs Capacitor vs React Native shell.
2. API/mobile contract hardening (stable endpoints, auth/session patterns).
3. App shell prototype for both iOS/Android.
4. Offline cache baseline (latest station/run state).
5. Store-ready build/release pipeline.

---

## EPIC 2 — ALERT Accumulator Conversion Toolkit

**Goal:** Add binary/decimal rollover and increment conversion tools for ALERT rainfall/water-level accumulators.

### Scope
- Convert raw binary payload fields to engineering units.
- Handle rollover boundaries and wrap detection.
- Support per-station calibration/scaling factors.
- Provide traceable conversion logs (raw -> converted -> corrected).

### Milestones
1. Conversion rules engine + test vectors.
2. UI utility page/tool for manual and batch conversion.
3. Integration into packets/forensics views.

---

## EPIC 3 — Benchmark + PSM Metadata

**Goal:** Record and manage benchmark details, including PSM information.

### Scope
- Station benchmark registry (coordinates, benchmark IDs, epoch/date, notes).
- PSM attributes and provenance.
- Import/export formats for field and office workflows.

### Milestones
1. Schema definition for benchmark + PSM records.
2. CRUD UI and API.
3. Link benchmark records to station map/catchment views.

---

## EPIC 4 — Catchment Hydraulics: Travel Times + Schematics

**Goal:** Add stream travel-time modeling and catchment schematic visualization.

### Scope
- Define reaches/nodes and travel-time parameters.
- Render schematic topology and route timing overlays.
- Scenario tools for event routing estimates.

### Milestones
1. Reach/node data model.
2. Schematic renderer + editor.
3. Travel-time calculator and report export.

---

## EPIC 5 — Field Wiring References

**Goal:** Provide field-ready wiring diagrams and pinouts (DB9 serial, null modem, etc.).

### Scope
- Canonical diagrams for common telemetry/radio/logger connections.
- Pinout library with printable quick sheets.
- Versioned diagram assets + change history.

### Milestones
1. Diagram template and asset repository.
2. Initial DB9/null modem pack.
3. In-app viewer + downloadable PDFs.

---

## EPIC 6 — Survey Recorder + Datum Reductions

**Goal:** Capture stream cross-sections and gauge geometry with datum reduction workflows (AHD, LGH, etc.).

### Scope
- Field recorder for cross-sections, gauge boards, orifice heights, bed slope.
- Datum conversion/reduction workflows with audit trail.
- Attach photos/sketches/notes to survey runs.

### Milestones
1. Survey data schema and unit conventions.
2. Recorder UI + validation.
3. Datum reduction engine and report output.

---

## EPIC 7 — Offline-First Operations

**Goal:** Maximize offline storage and function continuity (station-specific and run-specific bins/workspaces).

### Scope
- Local-first caches for stations, runs, packets, and key tools.
- Sync/reconcile when connectivity returns.
- Explicit offline mode UX + conflict handling.

### Milestones
1. Offline storage architecture (web + mobile).
2. Run-specific bin/workspace model.
3. Sync conflict policies and operator tooling.

---

## Implementation Notes
- Keep single-repo strategy with shared domain logic and API-first contracts.
- Prefer additive modules over app-specific forks.
- Build in test fixtures for conversion/survey/hydraulic computations early.
