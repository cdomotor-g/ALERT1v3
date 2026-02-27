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

## Migration status

Internal runtime artifacts now have canonical neutral names with compatibility wrappers:

- `src/fwlab_receiver.py` (canonical runtime entrypoint)
- `src/fwlab_epy_logger.py`
- `src/fwlab_epy_decoder.py`
- `src/fwlab_epy_mqtt.py`

Legacy compatibility wrappers retained:
- `src/ALERT1v3.py`
- `src/ALERT1v3_epy_block_0.py`
- `src/ALERT1v3_epy_block_1.py`
- `src/ALERT1v3_epy_block_2.py`

This allows safe migration while preserving existing flowgraph/module references.
