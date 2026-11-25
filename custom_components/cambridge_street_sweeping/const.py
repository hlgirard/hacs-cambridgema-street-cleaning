"""Constants for the Cambridge Street Cleaning integration."""

from typing import Final

DOMAIN: Final = "cambridge_street_sweeping"

CONF_DEVICE_TRACKER: Final = "device_tracker_entity"

VERSION: Final = "0.3.1"
REPO_URL: Final = "https://github.com/hlgirard/hacs-cambridgema-street-cleaning"
USER_AGENT: Final = f"HA-CambridgeStreetCleaning/{VERSION} (+{REPO_URL})"

NOMINATIM_URL: Final = "https://nominatim.openstreetmap.org/reverse"

# The city's GIS layer keeps the "Sweeping" name.
CLEANING_DISTRICTS_URL: Final = (
    "https://services1.arcgis.com/WnzC35krSYGuYov4/arcgis/rest/services/"
    "Street_Sweeping_Districts/FeatureServer/0/query"
)

CENTERLINE_URL: Final = (
    "https://services1.arcgis.com/WnzC35krSYGuYov4/ArcGIS/rest/services/"
    "Centerline_Web/FeatureServer/0/query"
)

MASTER_ADDRESS_LIST_URL: Final = (
    "https://services1.arcgis.com/WnzC35krSYGuYov4/ArcGIS/rest/services/"
    "Master_Address_List_New/FeatureServer/0/query"
)

UPDATE_INTERVAL_MINUTES: Final = 30

# Minimum distance (meters) the car must move before we re-query the APIs.
MIN_MOVEMENT_METERS: Final = 50

REQUEST_TIMEOUT_SECONDS: Final = 10

# Only addresses this close to the car vote on the side of the street.
MAX_ADDRESS_DISTANCE_METERS: Final = 150

ISSUE_SCHEDULE_EXPIRED: Final = "schedule_expired"
