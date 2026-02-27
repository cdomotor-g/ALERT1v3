# Data Model and Contracts

## Event contract (node -> local -> archive -> viewer)

Schema namespace:
- `alert.*` (current compatibility baseline)

Required top-level fields:
- `schema`
- `ts`
- `node_id` (to be enforced for multi-node scale)
- `status`

Recommended payload shape:

```json
{
  "schema": "alert.decode.v1",
  "ts": "2026-01-01T12:00:00Z",
  "node_id": "rxnode-au-bris-01",
  "status": "ok",
  "rx": {
    "center_freq_hz": 173900000,
    "rf_gain_db": 40,
    "rf_squelch_db": -33
  },
  "quality": {
    "score": 0.92,
    "confidence": "high",
    "ones_ratio": 0.51
  },
  "errors": [],
  "decode": {
    "sensor_id": 1234,
    "format_id": 1,
    "is_binary": false,
    "data_val": 456
  },
  "frame": {
    "payload_hex": "A1B2C3D4",
    "payload_bits": "..."
  },
  "summary": "1234, 000456"
}
```

## Archive object model (DCS)

Object key pattern (example):
- `events/node_id=rxnode-au-bris-01/date=2026-02-27/hour=13/chunk_20260227T130000Z_0001.jsonl.gz`

Manifest fields (example):
- `node_id`
- `object_key`
- `sha256`
- `first_ts` / `last_ts`
- `event_count`
- `uploaded_at`

## Node metadata model

- `node_id` (stable unique id)
- `display_name`
- `region`
- `lat` / `lon` (when available)
- `frequencies` / profiles
- `software_version`

## Geospatial readiness

For map features, ensure enrichment path exists for:
- sensor-to-location mapping
- node geolocation
- optional confidence/quality overlays on map layers

## Versioning

- Maintain explicit schema versions (`*.v1`, `*.v2`)
- Avoid breaking payload shape without version bump
- Keep source compatibility adapters when rolling versions
