# Cambridge Street Sweeping

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that tracks the next street sweeping date in Cambridge, MA based on a GPS-tracked vehicle's location.

## How it works

1. Monitors a `device_tracker` entity (e.g., your car) for GPS coordinates
2. Queries the [Cambridge Street Sweeping Districts](https://services1.arcgis.com/WnzC35krSYGuYov4/arcgis/rest/services/Street_Sweeping_Districts/FeatureServer) layer (point-in-polygon) to determine the sweeping district
3. Reverse geocodes via [Nominatim/OpenStreetMap](https://nominatim.openstreetmap.org/) to get the street address and house number (for accurate odd/even side determination)
4. Looks up the next scheduled sweeping date from the 2026 city schedule
5. Exposes a sensor entity with the result

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
| **State** | Next sweeping date (ISO format, e.g. `2026-06-01`) or `None` if outside Cambridge |
| `district` | Sweeping district letter (A-K) |
| `side` | `odd` or `even` (based on nearest street number) |
| `nearest_address` | Closest Cambridge address to GPS position |
| `next_sweep_formatted` | Human-readable date (e.g. "Monday, June 01, 2026") |
| `in_cambridge` | Whether the vehicle is currently in Cambridge |

## Update behavior

- Polls the GPS entity every **30 minutes**
- Only re-queries the Cambridge API if the vehicle has moved more than **50 meters**
- When stationary, still recalculates the next date (in case a sweep date has passed)

## Schedule data

The 2026 schedule is sourced from the [City of Cambridge DPW](https://www.cambridgema.gov/services/streetcleaning). When the schedule expires (all dates passed), the sensor state becomes `schedule_expired` with a warning attribute.

## Data sources

- **District lookup (point-in-polygon):** [Cambridge Street Sweeping Districts Feature Service](https://services1.arcgis.com/WnzC35krSYGuYov4/arcgis/rest/services/Street_Sweeping_Districts/FeatureServer)
- **Reverse geocoding (street + house number):** [Nominatim / OpenStreetMap](https://nominatim.openstreetmap.org/)
- **District boundaries GeoJSON:** [cambridgegis/cambridgegis_data_dpw](https://github.com/cambridgegis/cambridgegis_data_dpw)
- **Schedule PDF:** [cambridgema.gov/services/streetcleaning](https://www.cambridgema.gov/services/streetcleaning)
