# Architecture Vision

This document captures the target system vision for the Flood Warning platform.

## Platform scope

Primary domain:
- `floodwarning.net` (portal / landing)

Planned role-based surfaces:
- `nodes.floodwarning.net` — RXNODE operations and monitoring
- `data.floodwarning.net` — data exploration and analytics
- `api.floodwarning.net` — API services and machine integrations

## Core components

- **RXNODE**: edge receiver node running SDR + decode pipeline
- **DCS (Data Cold Storage)**: centralized long-term archive (S3-compatible)
- **RXNODE Interface**: operator UI for node monitoring/configuration
- **DataViewer**: multi-user web application for time-series exploration
- **Control Plane**: identity, authorization, node registry, config, audit

## Design principles

1. **Edge-first reliability**
   - RXNODE continues decoding with local storage when upstream is unavailable.
2. **Append-only archival**
   - DCS stores immutable chunked artifacts (`jsonl.gz`) + manifests.
3. **Schema-first interoperability**
   - Shared event contracts across node, archive, and viewer.
4. **Separation of concerns**
   - Node operations, archive workflows, and analytics UIs evolve independently.
5. **Security by default**
   - Strong auth, scoped roles, audited actions, no broad raw service exposure.

## Scale target

- Support multiple geographically distributed RXNODEs.
- Support multiple frequencies and receiver profiles.
- Support multi-user DataViewer access over web.

## Deployment evolution

Current:
- Pi-hosted development deployment.

Target:
- Portal/API/control services on more suitable home-lab or cloud hosts.
- RXNODE services distributed at edge sites.
- DCS hosted in cloud object storage.
