# Path Analysis API (MVP draft)

Parent epic: #38  
Initial implementation target: #39

This document defines a versioned request/response contract for single-link path analysis.

## Endpoints (current MVP)

- `POST /api/path/analyze`
- `POST /api/path/compare` (same as analyze + optional measured comparison block)

## Request schema (`fwlab.path.request.v1`)

```json
{
  "schema": "fwlab.path.request.v1",
  "tx": {
    "name": "Site A",
    "lat": -27.4698,
    "lon": 153.0251,
    "antenna_agl_m": 10.0
  },
  "rx": {
    "name": "Site B",
    "lat": -27.5600,
    "lon": 152.9800,
    "antenna_agl_m": 8.0
  },
  "rf": {
    "frequency_mhz": 173.9,
    "tx_power_dbm": 37.0,
    "tx_antenna_gain_dbi": 3.0,
    "rx_antenna_gain_dbi": 3.0,
    "tx_system_loss_db": 1.5,
    "rx_system_loss_db": 1.5,
    "rx_sensitivity_dbm": -110.0
  },
  "measured": {
    "rx_dbm": -89.5
  },
  "model": {
    "mode": "fspl_mvp",
    "reliability_percent": 50,
    "climate": "continental_temperate",
    "polarization": "vertical",
    "time_percent": 50,
    "location_percent": 50
  },
  "sampling": {
    "profile_step_m": 30,
    "max_points": 4000
  }
}
```

### Required fields

- `schema`
- `tx.lat`, `tx.lon`, `tx.antenna_agl_m`
- `rx.lat`, `rx.lon`, `rx.antenna_agl_m`
- `rf.frequency_mhz`, `rf.tx_power_dbm`, `rf.rx_sensitivity_dbm`

### Validation rules (MVP)

- Latitude: `-90..90`
- Longitude: `-180..180`
- `frequency_mhz > 0`
- `antenna_agl_m >= 0`
- `profile_step_m >= 5`
- `max_points <= 20000`

## Response schema (`fwlab.path.result.v1`)

```json
{
  "schema": "fwlab.path.result.v1",
  "ts": "2026-03-06T01:30:00Z",
  "request_schema": "fwlab.path.request.v1",
  "summary": {
    "distance_km": 12.34,
    "path_loss_db": 126.7,
    "predicted_rx_dbm": -86.2,
    "fade_margin_db": 23.8,
    "margin_class": "good"
  },
  "budget": {
    "tx_power_dbm": 37.0,
    "tx_antenna_gain_dbi": 3.0,
    "tx_system_loss_db": 1.5,
    "path_loss_db": 126.7,
    "rx_antenna_gain_dbi": 3.0,
    "rx_system_loss_db": 1.5,
    "predicted_rx_dbm": -86.2,
    "rx_sensitivity_dbm": -110.0,
    "fade_margin_db": 23.8
  },
  "profile": {
    "distance_m": [0, 30, 60],
    "terrain_m_asl": [45.0, 45.1, 45.3],
    "los_m_asl": [55.0, 54.9, 54.8],
    "fresnel60_radius_m": [0.0, 5.1, 7.2],
    "clearance_m": [10.0, 9.8, 9.5]
  },
  "assumptions": {
    "propagation_model": "itm_parity",
    "dem_source": "SRTM",
    "dem_resolution_m": 30,
    "reliability_percent": 50,
    "location_percent": 50,
    "time_percent": 50
  },
  "warnings": [],
  "parity": {
    "measured_rx_dbm": -89.5,
    "delta_db": 3.3,
    "fit_class": "ok"
  }
}
```

## Margin classes (MVP)

- `good`: `fade_margin_db >= 20`
- `marginal`: `10 <= fade_margin_db < 20`
- `poor`: `< 10`

## Error response

```json
{
  "ok": false,
  "error": "validation_error",
  "details": ["tx.lat out of range"]
}
```

## Interim model modes currently available

- `fspl_mvp`: free-space baseline only
- `fspl_diffraction_proxy`: FSPL plus interim obstruction penalty derived from Fresnel clearance

> The diffraction proxy is a temporary engineering aid, not final Radio Mobile parity.

## Notes

- This is a calculator contract only; propagation engine specifics are implemented in #40.
- Radio Mobile parity validation scenarios are tracked in epic #38.
