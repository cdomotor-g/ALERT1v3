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
- Continue extracting remaining read-only analytics endpoints (`forensics_bundle`, `pair_pattern_stats`, etc.).
- Build a final route ownership pass and remove any lingering dead/duplicate inline route blocks.
- Run endpoint parity sweep (status codes/shape) for all moved routes.
