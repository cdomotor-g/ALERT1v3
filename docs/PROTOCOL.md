# ALERT Protocol Decode Notes (Working Draft)

> Status: reverse-engineering + implementation notes from `ALERT1v3_epy_block_1.py`.
> This doc should be refined against captured known-good frames.

## 1) Decoder State Machine (current)

- `HUNTING_S`: waits for a logical start condition (`bit == 1`)
- `COLLECTING_WORD`: captures a 10-bit word
- For each 10-bit word:
  - first bit treated as start/sync marker
  - next 8 bits are payload bits (`[1:9]`)
  - one trailing bit effectively ignored (likely stop/parity placeholder)
- After 4 words, 32 payload bits are reassembled into one message integer

So current parser model is effectively:
- 4 words × 8 payload bits = 32 payload bits per decoded frame

## 2) Current Field Extraction (from code)

Given `msg_int`:

- `sensor_id`:
  - bits `[0..5]`
  - plus bits `[8..13]` shifted into upper field
  - plus bit `[16]` as top bit
  - total assembled width: 13 bits

- `format_id`:
  - bits `[6..7]` (2 bits)

- `is_binary`:
  - `True` when `format_id == 2`

- `data_val`:
  - bits `[17..21]`
  - plus bits `[24..29]` shifted left by 5
  - total assembled width: 11 bits

Current debug output prints:
- `"{sensor_id:04d}, {data_val:06d}"`

## 3) Gaps / Unknowns to Resolve

- Exact bit ordering convention (MSB/LSB per subfield) should be validated with captures
- Role of discarded per-word bit (parity? stop? delimiter?)
- Integrity checks (checksum/parity/CRC) are currently absent
- No explicit framing confidence metric yet

## 4) Decoded Event Schema (v1, current implementation)

```json
{
  "schema": "alert.decode.v1",
  "ts": "2026-01-01T12:00:00Z",
  "status": "ok",
  "rx": {
    "center_freq_hz": 173900000.0,
    "rf_gain_db": -1.0,
    "rf_squelch_db": -33.0
  },
  "frame": {
    "bits_per_word": 10,
    "word_count": 4,
    "payload_bits": "010101...",
    "payload_hex": "A1B2C3D4"
  },
  "decode": {
    "sensor_id": 1234,
    "format_id": 2,
    "is_binary": true,
    "data_val": 321
  },
  "summary": "1234, 000321",
  "display": "1234, 000321"
}
```

Notes:
- `summary` remains the stable human-readable line for operator views.
- `display` duplicates `summary` to keep GUI-oriented paths explicit.
- `status` can be `ok`, `warn`, or `error`.

Quality and errors (current decoder):
- `quality.score` (0.0-1.0)
- `quality.confidence` (`high` / `medium` / `low`)
- `quality.ones_ratio`
- `errors[]` with `{code, message}`

Current error taxonomy includes:
- `timing.hunt_timeout`
- `pipeline.output_overflow`
- `framing.length_mismatch`
- `framing.word_start_stop_mismatch`
- `decode.invalid_format_id`
- `decode.zero_payload`
- `decode.zero_sensor_id`
- `decode.strict_reject`
- `signal.bit_balance_extreme`

Decoder framing model (current):
- 10-bit words parsed as `start + 8 data + stop`
- configurable start/stop polarity
- configurable data-bit ordering (`word_lsb_first`)
- optional input inversion (`invert_bits`)
- strict mode gate to suppress obviously invalid decodes

## 5) Next decoder improvements

1. Tune quality heuristics against known-good and known-bad captures
2. Add optional checksum/parity verification when protocol evidence is available
3. Extend replay assertions with negative/noisy fixture cases
4. Add optional AFSK profile controls (mark/space tone settings) for OEM parity experiments:
   - `afsk_mark_hz` default `2100.0`
   - `afsk_space_hz` default `1300.0`
   - `demod_mode` default `legacy_fsk` (no behavior change yet; telemetry scaffold only)

### Acceptance criteria for AFSK parity trial

Live monitoring endpoint:
- `GET /api/anomaly_stats?limit=4000`
- Tracks counts and percentages for:
  - `sensor_id=0`
  - `data_val=0`
  - `sensor_id=8191`
  - `data_val=2047` (`002047` display form)
  - tuple `8191/2047`


- Maintain existing decode stability in `legacy_fsk` mode (no regression in frame rate/errors).
- In A/B trials against OEM-style captures, reduce incidence of known anomalous tuples:
  - `sensor_id=8191`
  - `data_val=002047`
- Continue reducing historic anomaly buckets during remediation:
  - `sensor_id=0`
  - `data_val=0`
