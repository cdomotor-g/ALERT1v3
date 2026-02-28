# Access model and governance

This document defines the control-plane access posture for FW-LAB.

## Roles

- **viewer**
  - read dashboard/trends/events
  - no write/control actions

- **operator**
  - viewer permissions
  - receiver start/stop/restart
  - RF control writes

- **admin**
  - operator permissions
  - storage/archive policy writes
  - governance/config actions

## Current implementation status

- Cloudflare Access is the primary remote identity gate.
- Local admin API guard scaffold exists via `config/access_policy.json`:
  - `adminApi.enabled`
  - `adminApi.token`
  - `adminApi.allowLocalhostWithoutToken`

When enabled, admin API write endpoints require `X-Admin-Token` header unless request is localhost and localhost bypass is enabled.

## Audit trail

Admin write actions are appended to:
- `rf_log/audit/admin_actions.jsonl`

Each entry includes:
- timestamp
- action
- remote address
- outcome (ok/error)
- minimal sanitized details

## Operational guidance

- Keep Cloudflare Access allowlist strict.
- Enable admin API token for internet-exposed control surfaces.
- Rotate admin token periodically.
- Review audit log regularly.
