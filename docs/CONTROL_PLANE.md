# Control Plane (scaffold)

This repo now includes a role-driven control-plane scaffold.

## Role config

- `config/deployment_role.json`
- Roles: `edge`, `control`, `hybrid`

## Install/role helpers

- `scripts/install_fwlab.sh --profile auto --yes`
- `scripts/set_role.sh <edge|control|hybrid> --apply --verify`

## S3 state helpers

- Promote/bootstrap: `scripts/promote_control_plane.sh`
- Status: `scripts/control_plane_status.sh`
- Drill: `scripts/control_plane_drill.sh`

## Ingest policy

- `config/control_plane_policy.json`
  - `enabled`
  - `ingestToken`
  - `allowLocalhostWithoutToken`
  - `maxEventsPerIngest`
  - `ingestStateDir`

## APIs (new)

- `POST /api/control/ingest`
  - auth: `X-Control-Token` when policy enabled (or localhost allowed)
  - body: `{ rxs_id, events[], heartbeat{}, stats{} }`
- `GET /api/control/policy`
- `GET /api/control/receivers`
- `GET /api/control/receiver_latest?rxs_id=0000`
- `GET /api/receiver_proxy?rxs_id=0001&path=/api/events?limit=200`

## Notes

This is an incremental scaffold to support multi-receiver federation and failover drills.
It is not yet full HA consensus; promotion lock semantics are lease-based and intended as a safety guard.
