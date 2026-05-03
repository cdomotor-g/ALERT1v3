# ROUTING_MAP

Purpose: single-source endpoint ownership map to reduce rediscovery overhead.

## Route Modules

- `webui/routes_control.py`
  - `GET /api/control/policy`
  - `GET /api/control/state_summary`
  - `GET /api/control/receivers`
  - `GET /api/control/receiver_latest`
  - `GET /api/receiver_proxy`
  - `POST /api/control/ingest`

- `webui/routes_receivers.py`
  - `GET /api/receiver_info`
  - `GET /api/receivers_registry`
  - `POST /api/receivers_registry_update`

- `webui/routes_stations.py`
  - `GET /api/stations`
  - `GET /api/stations/catalog`
  - `GET /api/stations/rows`
  - `POST /api/stations/update`
  - `POST /api/stations/delete`
  - `POST /api/stations/upload`

- `webui/routes_filedrop.py`
  - `GET /api/file_drop/list`
  - `POST /api/file_drop/upload`

- `webui/routes_sensor_map.py`
  - `GET /api/sensor_map/status`

- `webui/routes_path_defaults.py`
  - `GET /api/path/defaults`
  - `POST /api/path/defaults`

- `webui/routes_meta.py`
  - `GET /api/meta/catalog`
  - `GET /api/meta/export`
  - `GET /api/deployment_role`

- `webui/routes_rx.py`
  - `GET /api/rx_agg`

- `webui/routes_events.py`
  - `GET /api/events`
  - `GET /api/sensors`

- `webui/routes_views.py`
  - `GET /api/views`
  - `POST /api/views`

- `webui/routes_stats.py`
  - `GET /api/error_stats`
  - `GET /api/anomaly_stats`

- `webui/routes_forensics.py`
  - `GET /api/forensics_bundle`
  - `GET /api/pair_pattern_stats`

- `webui/routes_docs_api.py`
  - `GET /api/flowgraph_doc`

- `webui/routes_status.py`
  - `GET /api/storage_status`
  - `GET /api/receiver_status`
  - `GET /api/host_metrics`

- `webui/routes_trends.py`
  - `GET /api/trends`

- `webui/routes_admin.py`
  - `GET /api/admin/storage_policy`
  - `GET /api/admin/rf_control`
  - `GET /api/admin/audit_recent`
  - `GET /api/admin/meta/history`
  - `POST /api/admin/storage_policy`
  - `POST /api/admin/rf_control`
  - `POST /api/admin/receiver_action`
  - `POST /api/admin/meta/catalog`

## Remaining in `webui/server.py` (high-level)
- SSE/audio streaming endpoints (e.g. `/api/live`, audio routes)
- HTML/template serving and static/resource handling
- Misc operational endpoints not yet grouped

Update this map with each extraction commit.
