# MQTT Output (Issue #5)

ALERT1v3 now includes an MQTT publisher block implementation at:
- `src/ALERT1v3_epy_block_2.py`

The MQTT block is wired by default in `src/ALERT1v3.grc` and receives decoder events via `debug_out`.

## Topics
With default prefix `alert`:
- `alert/rx/decoded` (full `alert.decode.v1` event)
- `alert/rx/raw` (frame-focused payload)
- `alert/rx/status` (status + summary + key IDs)
- `alert/rx/metrics` (publisher counters + connection status)

## Block parameters
- `broker_host` (default `127.0.0.1`)
- `broker_port` (default `1883`)
- `username` / `password`
- `topic_prefix` (default `alert`)

## Runtime config vars in the flowgraph
- `mqtt_broker_host`
- `mqtt_broker_port`
- `mqtt_username`
- `mqtt_password`
- `mqtt_topic_prefix`

## Notes
- Uses `paho-mqtt` when available.
- If unavailable, block stays non-fatal and logs an error (decode/log path remains live).
- Designed to preserve decoder behavior when MQTT is offline.
