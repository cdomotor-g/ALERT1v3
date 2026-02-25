# Architecture (Draft)

## 1) System Overview

ALERT1v3 has three conceptual layers:

1. **Signal Acquisition & DSP (GNU Radio)**
   - RTL-SDR source
   - Filtering/decimation
   - Squelch + demod + symbol sync

2. **Protocol Decode**
   - Frame hunting and word assembly
   - Field extraction (sensor_id, format_id, data value)
   - Decode status/debug events

3. **Outputs / Integrations**
   - On-screen diagnostics (Qt GUI)
   - File logging (CSV now, JSONL planned)
   - MQTT publish (planned)
   - Web UI backend/event stream (planned)

## 2) Current v3 Signal Paths

### A) Decode path
`RTL-SDR -> LPF/decim -> squelch -> quadrature demod -> AGC/LPF -> symbol sync -> protocol decoder`

### B) Audio monitor path
`RTL-SDR -> rational resampler -> WFM receive -> AGC -> audio sink`

### C) Debug/Logging path
`protocol decoder debug_out (message) -> GUI text + CSV logger`

## 3) Known Technical Debt

- Decoder block output signature mismatch (declared outputs vs used outputs in code)
- Decoder currently surfaces limited semantics to operator
- Logging payload is minimally structured
- UI mixes operator and engineering concerns in one dense run view

## 4) Target Architecture (v4 direction)

### Core principle
Keep SDR decode logic independent from integration/UI delivery.

### Proposed components

- **`decoder_core`** (embedded block or python module)
  - deterministic decode state machine
  - emits structured decode events

- **`event_formatter`**
  - normalizes payload schema
  - adds timestamps, quality/status metadata

- **`event_sinks`**
  - CSV sink
  - JSONL sink
  - MQTT sink

- **`backend_service`** (FastAPI, planned)
  - reads event stream/log tail
  - provides REST/WebSocket for web UI

- **`web_ui`**
  - operator dashboard, message table, simple metrics

## 5) Data Contract (high level)

All downstream systems should consume a shared event shape:

- `schema` (versioned)
- `ts`
- `rx` metadata (freq/gain/squelch)
- `decode` data (sensor_id, format_id, data_val, is_binary)
- `raw` optional (bitstring/hex)
- `status` (`ok`/error mode)
- `quality` (confidence/score placeholder)

This contract is the backbone for logs, MQTT, and UI.
