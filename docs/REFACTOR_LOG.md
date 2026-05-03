# REFACTOR_LOG

Purpose: compact, durable progress log for route modularization and related cleanup.

## 2026-05-03

### Completed
- Extracted control-plane routes to `webui/routes_control.py` and removed duplicate control GET blocks from `webui/server.py`.
- Added `webui/routes_receivers.py` for receiver registry/info GET+POST routes.
- Added `webui/routes_stations.py` for stations catalog/list/rows GET and update/delete/upload POST routes.
- Added `webui/routes_filedrop.py` for file drop list/upload routes.
- Added `webui/routes_sensor_map.py` for sensor map status route.
- Added `webui/routes_path_defaults.py` for path defaults GET+POST.
- Added `webui/routes_meta.py` for meta catalog/export + deployment role GET routes.
- Added `webui/routes_rx.py` for rx aggregate GET route.
- Added `webui/routes_events.py` for events/sensors GET routes.
- Added `webui/routes_views.py` for views GET+POST routes.
- Added `webui/routes_stats.py` for error/anomaly stats GET routes.

### Commit trail (today)
- 85d66ae
- a5db539
- 2b02001
- 29ff07d
- e501c0f
- be657a4
- 6df379d
- 1bdbb16
- c9ad7f8
- c8528e3
- 549611d
- 5cda05f
- c12a882
- 4428f75
- 6221af8
- f6235ed
- 893fa6b
- b5ee9b1

### Next
- Keep Phase 3 optional: decide whether to isolate SSE/audio routes or intentionally keep them in `server.py`.
- Run endpoint parity sweep (status codes/shape) for all moved routes.

### Additional completed (post-log)
- Added `webui/routes_forensics.py` for `GET /api/forensics_bundle` and `GET /api/pair_pattern_stats`.
- Added `webui/routes_docs_api.py` for `GET /api/flowgraph_doc`.
- Added `webui/routes_status.py` for `GET /api/storage_status`, `GET /api/receiver_status`, `GET /api/host_metrics`.
- Added `webui/routes_trends.py` for `GET /api/trends`.
- Added `webui/routes_admin.py` for admin GET+POST routes with centralized auth/audit gate.
- Confirmed no duplicate inline handlers remain in `server.py` for moved route families.

### Additional commit trail
- 74b9846
- f87de09
- d61e905
- 19eaade
- 3266ea4
- c34cf6f
