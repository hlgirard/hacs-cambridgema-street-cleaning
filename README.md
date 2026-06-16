# Cambridge Street Sweeping

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that tracks the next street sweeping date in Cambridge, MA based on a GPS-tracked vehicle's location.

## How it works

1. Monitors a `device_tracker` entity (e.g., your car) for GPS coordinates.
2. Queries the [Cambridge Street Sweeping Districts](https://services1.arcgis.com/WnzC35krSYGuYov4/arcgis/rest/services/Street_Sweeping_Districts/FeatureServer) layer (point-in-polygon) to determine the sweeping district.
3. Reverse geocodes via [Nominatim/OpenStreetMap](https://nominatim.openstreetmap.org/) to get the street name.
4. Refines the side-of-street resolution by determining the car's position relative to the street's centerline (queried from the Cambridge GIS `Centerline_Web` layer) and mapping the target side (left/right) to the correct odd/even parity using nearby address points (from the Cambridge `Master_Address_List_New` layer). This ensures highly accurate side resolution even when the closest Nominatim address point is on the opposite side of the street.
5. Looks up the next scheduled sweeping date from the 2026 city schedule, inclusive of today (so the sensor state shows today's date when a sweep is scheduled on the day of).
6. Exposes a sensor entity with the result.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL with category "Integration"
5. Click "Download"
6. Restart Home Assistant

### Manual

Copy the `custom_components/cambridge_street_sweeping` directory into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for "Cambridge Street Sweeping"
3. Select the `device_tracker` entity for your vehicle

## Sensor

The integration creates a sensor entity with:

| Property | Description |
|----------|-------------|
| **State** | Next sweeping date (e.g. `2026-06-01`) or unavailable if outside Cambridge / schedule expired |
| `district` | Sweeping district letter (A-K) |
| `side` | `odd` or `even` (based on nearest street number) |
| `nearest_address` | Closest Cambridge address to GPS position |
| `next_sweep_formatted` | Human-readable date (e.g. "Monday, June 01, 2026") |
| `in_cambridge` | Whether the vehicle is currently in Cambridge |
| `schedule_expired` | `True` when the hardcoded calendar has no future dates |

The sensor uses `device_class: date` so tile cards render it as a friendly date. The icon switches from `mdi:broom` (green) to `mdi:alert` (orange) when the schedule is expired.

## Dashboard card

A simple tile card works out of the box:

```yaml
type: tile
entity: sensor.next_street_sweeping
```

To conditionally color the tile based on schedule state, use a [card-mod](https://github.com/thomasloven/lovelace-card-mod) style or a conditional card:

```yaml
type: conditional
conditions:
  - condition: state
    entity: sensor.next_street_sweeping
    state_not: unavailable
card:
  type: tile
  entity: sensor.next_street_sweeping
  color: green
```

## Update behavior

- Polls the GPS entity every **30 minutes**
- Only re-queries the Cambridge API if the vehicle has moved more than **50 meters**
- When stationary, still recalculates the next date (in case a sweep date has passed)

## Schedule data

The 2026 schedule is sourced from the [City of Cambridge DPW](https://www.cambridgema.gov/services/streetcleaning). When the schedule expires (all dates passed), the sensor becomes unavailable with a `schedule_expired: True` attribute and the icon switches to a warning indicator.

## Data sources

- **District lookup (point-in-polygon):** [Cambridge Street Sweeping Districts Feature Service](https://services1.arcgis.com/WnzC35krSYGuYov4/arcgis/rest/services/Street_Sweeping_Districts/FeatureServer)
- **Street centerlines:** [Cambridge Centerline Web Feature Service](https://services1.arcgis.com/WnzC35krSYGuYov4/ArcGIS/rest/services/Centerline_Web/FeatureServer)
- **Address points:** [Cambridge Master Address List Feature Service](https://services1.arcgis.com/WnzC35krSYGuYov4/ArcGIS/rest/services/Master_Address_List_New/FeatureServer)
- **Reverse geocoding (street + house number):** [Nominatim / OpenStreetMap](https://nominatim.openstreetmap.org/)
- **District boundaries GeoJSON:** [cambridgegis/cambridgegis_data_dpw](https://github.com/cambridgegis/cambridgegis_data_dpw)
- **Schedule PDF:** [cambridgema.gov/services/streetcleaning](https://www.cambridgema.gov/services/streetcleaning)
