# Components and Responsibilities

## 1) Domain Portal (`floodwarning.net`)

Responsibilities:
- User entrypoint to platform tools
- Links to node interface, dataviewer, docs/status

Notes:
- Can remain lightweight and stateless
- Should not directly host heavy node runtime logic long-term

## 2) RXNODE

Responsibilities:
- SDR acquisition + demod + decode
- Local hot retention and health telemetry
- Publish integrations (MQTT/UDP as configured)
- Archive export handoff to DCS pipeline

Key node metadata:
- `node_id`
- location descriptor
- receiver profile/frequency

## 3) DCS (Centralized Data Cold Storage)

Responsibilities:
- Long-term immutable storage of event chunks
- Retention and lifecycle policy management
- Archive manifest/index hosting

Initial backend target:
- S3-compatible object storage (R2/B2/S3)

## 4) RXNODE Interface

Responsibilities:
- Fleet view (all nodes)
- Node detail view (status, controls, diagnostics)
- Safe operational controls with role checks

Recommended UX model:
- Single interface with node selector, not separate UI per node

## 5) DataViewer

Responsibilities:
- Time-series and exploratory visualization
- Multi-user web access
- Read-only analytics initially

Planned capabilities:
- rich filtering and saved views
- derived metrics (delta/rate-of-rise)
- geospatial map-based exploration

## 6) Control Plane

Responsibilities:
- Authentication and authorization
- Node registry and config distribution
- Audit trail for operator actions
- Job orchestration and policy distribution

Rationale:
- Essential for safe multi-node operations at scale
