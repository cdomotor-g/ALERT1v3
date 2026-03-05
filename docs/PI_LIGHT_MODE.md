# Pi-light Mode (Receiver Node)

Goal: keep Raspberry Pi focused on RF ingest + decode reliability, while reducing local UI/analytics cost.

## Profiles

## `full-local` (current default)
- Local pages: `/`, `/events`, `/radio`, `/data`, `/forensics`, `/admin`, `/about`
- Good for standalone operation, highest local resource use.

## `pi-light` (recommended for unattended ops)
- Keep local usage focused on:
  - `/events` (operational event stream)
  - `/radio` (light health checks)
  - `/admin` (control plane fallback)
- Move heavy usage off-prem:
  - `/data` long-window analytics
  - `/forensics` deep scans/exports

## Quick toggles checklist

1. Reduce polling cadence in local dashboard/UI.
2. Prefer sidecar summaries over raw log scans.
3. Keep browser audio monitor opt-in (disabled until user activates).
4. Avoid prolonged `/forensics` use on Pi during active RF operations.
5. Use remote UI for historical analysis (archive/cold-heavy queries).

## Sidecar-first guidance

- Use sidecars for pre-aggregated telemetry:
  - RX bins (2m/30m)
  - error code rates
  - pair-pattern stats
- UI should consume sidecar JSON endpoints first, fallback to local scans only when needed.

## Security

- Keep receiver control endpoints protected (token policy / localhost policy as required).
- Expose local UI only on trusted networks (Tailscale and/or restricted LAN CIDR).

## Rollout plan

1. Baseline host metrics (24h).
2. Enable quick toggles.
3. Compare 24h metrics.
4. Shift `/data` + `/forensics` daily usage to remote control-plane.
5. Keep local fallback pages for outages/recovery.

## Acceptance checks

- Receiver decode stability unchanged or improved.
- Lower sustained CPU/RAM on Pi.
- Remote analytics pages fully usable.
- Local fallback admin/events still functional.
