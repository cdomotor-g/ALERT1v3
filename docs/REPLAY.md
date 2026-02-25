# Replay / Validation Fixture

This project now includes a one-command replay path to validate the decoder → logger → web/MQTT chain without RF hardware.

## Command

```bash
./tools/replay_validate.sh
```

What it does:
1. Starts a local temporary Mosquitto broker
2. Subscribes to `alert/rx/#`
3. Replays synthetic ALERT frames through:
   - `ALERT1v3_epy_block_1` (decoder)
   - `ALERT1v3_epy_block_0` (logger)
   - `ALERT1v3_epy_block_2` (MQTT publisher)
4. Starts the web backend (`webui/server.py`) on the generated JSONL file
5. Verifies all three paths received events

Success output includes:
- `jsonl_lines` (logger)
- `mqtt_lines` (broker capture)
- `web_count` (web API event count)

## Optional overrides

- `MQTT_PORT` (default `18884`)
- `MQTT_PREFIX` (default `alert`)

Example:

```bash
MQTT_PORT=18890 MQTT_PREFIX=alert ./tools/replay_validate.sh
```
