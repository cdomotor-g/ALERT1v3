# Host monitor soak report (2026-02-26)

## Scope

Quick baseline soak of host monitor sidecar on Raspberry Pi.

- Duration: ~45 seconds
- Interval: 2s
- Samples: 23
- Source log: `rf_log/host_metrics_soak.jsonl`
- Summary: `rf_log/host_metrics_soak_summary.json`

## Results

- Status counts: `ok=23`, `warn=0`
- CPU %: min `0.0`, max `2.628`, avg `0.711`, p95 `1.258`
- RAM %: min `46.999`, max `47.103`, avg `47.057`, p95 `47.094`
- Disk %: `86.816` constant
- Temp C: min `51.121`, max `53.069`, avg `52.053`, p95 `53.069`
- Load/core (1m): min `0.007`, max `0.047`, avg `0.013`, p95 `0.014`

## Notes

- No threshold breaches under idle/light activity.
- Disk usage is relatively high (~86.8%); monitor should remain enabled and retention controls (#9) prioritized.
