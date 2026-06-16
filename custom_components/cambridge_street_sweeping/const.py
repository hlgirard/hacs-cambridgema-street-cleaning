"""Constants for Cambridge Street Sweeping integration."""

from datetime import date

DOMAIN = "cambridge_street_sweeping"

CONF_DEVICE_TRACKER = "device_tracker_entity"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

SWEEPING_DISTRICTS_URL = (
    "https://services1.arcgis.com/WnzC35krSYGuYov4/arcgis/rest/services/"
    "Street_Sweeping_Districts/FeatureServer/0/query"
)

CENTERLINE_URL = (
    "https://services1.arcgis.com/WnzC35krSYGuYov4/ArcGIS/rest/services/"
    "Centerline_Web/FeatureServer/0/query"
)

MASTER_ADDRESS_LIST_URL = (
    "https://services1.arcgis.com/WnzC35krSYGuYov4/ArcGIS/rest/services/"
    "Master_Address_List_New/FeatureServer/0/query"
)

UPDATE_INTERVAL_MINUTES = 30

# Minimum distance (meters) the car must move before we re-query the APIs.
MIN_MOVEMENT_METERS = 50

SCHEDULE_YEAR = 2026

# 2026 Street Cleaning Schedule
# Source: cambridgema.gov/services/streetcleaning (2026 PDF)
# Key: (district, side) -> list of (month, day) tuples
# Dates with * in the original have been adjusted for holidays.
SCHEDULE: dict[tuple[str, str], list[tuple[int, int]]] = {
    ("A", "odd"): [(4, 1), (5, 6), (6, 3), (7, 1), (8, 5), (9, 2), (10, 7), (11, 4), (12, 2)],
    ("A", "even"): [(4, 2), (5, 7), (6, 4), (7, 2), (8, 6), (9, 3), (10, 1), (11, 5), (12, 3)],
    ("B", "odd"): [(4, 6), (5, 4), (6, 1), (7, 6), (8, 3), (8, 31), (10, 5), (11, 2), (12, 7)],
    ("B", "even"): [(4, 7), (5, 5), (6, 2), (7, 7), (8, 4), (9, 8), (10, 6), (11, 3), (12, 1)],
    ("C", "odd"): [(4, 3), (5, 1), (6, 5), (6, 30), (8, 7), (9, 4), (10, 2), (11, 6), (12, 4)],
    ("C", "even"): [(4, 13), (5, 11), (6, 8), (7, 13), (8, 10), (9, 14), (9, 29), (11, 9), (12, 14)],
    ("D", "odd"): [(4, 14), (5, 12), (6, 9), (7, 14), (8, 11), (9, 8), (10, 13), (11, 10), (12, 8)],
    ("D", "even"): [(4, 8), (5, 13), (6, 10), (7, 8), (8, 12), (9, 9), (10, 14), (10, 29), (12, 9)],
    ("E", "odd"): [(4, 9), (5, 14), (6, 11), (7, 9), (8, 13), (9, 10), (10, 8), (11, 12), (12, 11)],
    ("E", "even"): [(4, 10), (5, 8), (6, 12), (7, 10), (8, 14), (9, 11), (10, 9), (11, 13), (12, 11)],
    ("F", "odd"): [(4, 29), (5, 18), (6, 15), (7, 20), (8, 17), (9, 21), (10, 19), (11, 16), (12, 21)],
    ("F", "even"): [(4, 21), (5, 19), (6, 16), (7, 21), (8, 18), (9, 15), (10, 20), (11, 17), (12, 15)],
    ("G", "odd"): [(4, 15), (5, 20), (6, 17), (7, 15), (8, 19), (9, 16), (10, 21), (11, 18), (12, 16)],
    ("G", "even"): [(4, 16), (5, 21), (6, 18), (7, 16), (8, 20), (9, 17), (10, 15), (11, 19), (12, 17)],
    ("H", "odd"): [(4, 17), (5, 15), (6, 29), (7, 17), (8, 21), (9, 18), (10, 16), (11, 20), (12, 18)],
    ("H", "even"): [(4, 27), (5, 29), (6, 22), (7, 27), (8, 24), (9, 28), (10, 26), (11, 23), (12, 28)],
    ("J", "odd"): [(4, 28), (5, 26), (6, 23), (7, 28), (8, 25), (9, 22), (10, 27), (11, 24), (12, 22)],
    ("J", "even"): [(4, 22), (5, 27), (6, 24), (7, 22), (8, 26), (9, 23), (10, 28), (11, 25), (12, 23)],
    ("K", "odd"): [(4, 23), (5, 28), (6, 25), (7, 23), (8, 27), (9, 24), (10, 22), (11, 30), (12, 24)],
    ("K", "even"): [(4, 24), (5, 22), (6, 26), (7, 24), (8, 28), (9, 25), (10, 23), (11, 27), (12, 29)],
}


def get_next_sweep_date(
    district: str, street_number: int, after: date | None = None
) -> date | None:
    """Return the next sweeping date for a district+side, or None if schedule expired."""
    if after is None:
        after = date.today()

    side = "odd" if street_number % 2 == 1 else "even"
    schedule_dates = SCHEDULE.get((district, side))
    if schedule_dates is None:
        return None

    for month, day in schedule_dates:
        try:
            sweep_date = date(SCHEDULE_YEAR, month, day)
        except ValueError:
            continue
        if sweep_date >= after:
            return sweep_date

    return None
