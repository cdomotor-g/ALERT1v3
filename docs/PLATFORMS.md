# Platform support matrix

Product: **FW-LAB Receiver**

## Support levels

- **Tier 1 (validated):** actively tested target for runtime workflows
- **Tier 2 (planned):** expected to work with partial validation
- **Tier 3 (future):** roadmap target, not yet implemented

## Matrix (v0.2)

| Platform | SDR decode path | Web UI | Perf sidecar | MQTT path | Status |
|---|---|---|---|---|---|
| Raspberry Pi OS (Debian, arm64) | Yes | Yes | Yes (linux adapter) | Yes | Tier 1 |
| Linux x86_64 (Debian/Ubuntu class) | Expected | Yes | Yes (linux adapter) | Yes | Tier 2 |
| macOS (Apple Silicon/Intel) | Partial/Unknown (GNU Radio + SDR driver dependent) | Yes | Planned adapter | Yes | Tier 3 |
| Windows 10/11 | Partial/Unknown (GNU Radio + SDR driver dependent) | Yes | Planned adapter | Yes | Tier 3 |

## Notes

- SDR compatibility depends heavily on device drivers and GNU Radio/Soapy/Osmosdr stack.
- Sidecars are designed to isolate OS-specific host metrics collection.
- Current perf monitor adapter is Linux-first (`linux_proc`).

## Capability check

Run host capability checks:

```bash
python3 tools/platform_capabilities.py
```

Optional JSON output:

```bash
python3 tools/platform_capabilities.py --json > capabilities.json
```

## Smoke checks

```bash
./tools/smoke_platform.sh
```

This validates core Python components and prints host capability status.
