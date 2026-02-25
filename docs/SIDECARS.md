# Sidecar architecture and naming

This project uses sidecars for non-DSP responsibilities (monitoring, replay, integration helpers).

## Why sidecars

- Keep GNU Radio decode path focused and stable.
- Isolate environment-specific concerns (OS metrics, services, packaging).
- Improve portability across Raspberry Pi and other host platforms.

## Layout

```text
sidecars/
  perf/
    monitor.py            # platform-neutral runner (implemented)
    adapters/
      linux_proc.py       # Linux /proc + thermal zone adapter (implemented)
      macos_ps.py         # future
      windows_wmi.py      # future
  replay/
    runner.py             # replay orchestration (future)
  mqtt/
    bridge.py             # optional external MQTT bridge (future)
```

Compatibility wrapper:
- `tools/host_monitor.py` forwards to `sidecars/perf/monitor.py` so existing scripts keep working.

## Naming conventions

- Product-facing: **FW-LAB Receiver**
- Event schemas: `alert.*` namespace retained for compatibility until schema version bump.
- Sidecar module names: `snake_case`, platform-neutral first (`monitor.py`) plus explicit adapters.

## Performance sidecar requirements

- Collect CPU, RAM, disk, temp, load with minimal overhead.
- Output JSONL and optional MQTT (`<prefix>/rx/host_metrics`).
- Emit threshold breaches consistently (`status: ok|warn`, `breaches[]`).
- Support configurable sample interval and thresholds.

## Multi-platform strategy

1. Define a common metric schema.
2. Implement Linux adapter first (current Pi baseline).
3. Add adapters for other target platforms incrementally.
4. Validate with replay/smoke scripts per platform.
