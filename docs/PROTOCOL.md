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
- `decode.invalid_format_id`
- `signal.bit_balance_extreme`

## 5) Next decoder improvements

1. Tune quality heuristics against known-good and known-bad captures
2. Add optional checksum/parity verification when protocol evidence is available
3. Extend replay assertions with negative/noisy fixture cases
