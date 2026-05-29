"""Data update coordinator for Cambridge Street Sweeping."""

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta

import requests

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    MIN_MOVEMENT_METERS,
    NOMINATIM_URL,
    SWEEPING_DISTRICTS_URL,
    UPDATE_INTERVAL_MINUTES,
    get_next_sweep_date,
)

_LOGGER = logging.getLogger(__name__)

UNRESOLVED_STATES = {STATE_UNKNOWN, STATE_UNAVAILABLE, None}


@dataclass
class SweepingData:
    """Sweeping lookup result."""

    district: str | None = None
    side: str | None = None
    nearest_address: str | None = None
    next_date: date | None = None
    schedule_expired: bool = False
    in_cambridge: bool = False


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance between two GPS points in meters."""
    r = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _reverse_geocode_nominatim(lat: float, lon: float) -> dict | None:
    """Reverse geocode via Nominatim to get street address and house number."""
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "addressdetails": 1,
        "zoom": 18,
    }
    headers = {"User-Agent": "CambridgeStreetSweepingHA/0.1"}
    resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    address = data.get("address", {})
    city = address.get("city", "")
    if "cambridge" not in city.lower():
        return None

    house_number_raw = address.get("house_number", "")
    # Nominatim may return "76;78" for interpolated addresses — take the first
    house_number = house_number_raw.split(";")[0].strip()
    road = address.get("road", "")

    if not house_number or not house_number.isdigit():
        return None

    return {
        "house_number": int(house_number),
        "road": road,
        "display": f"{house_number} {road}",
    }


def _query_sweep_district(lat: float, lon: float) -> str | None:
    """Query Cambridge Street Sweeping Districts layer for the district at a point."""
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "District",
        "returnGeometry": "false",
        "f": "json",
        "inSR": 4326,
    }
    resp = requests.get(SWEEPING_DISTRICTS_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    features = data.get("features", [])
    if not features:
        return None
    return features[0]["attributes"].get("District")


def _resolve_location(lat: float, lon: float) -> tuple[str | None, str | None, int | None]:
    """
    Resolve GPS to (district, display_address, house_number).

    Uses Nominatim for street/side and Cambridge Districts layer for district.
    Returns (None, None, None) if not in Cambridge.
    """
    district = _query_sweep_district(lat, lon)
    if district is None:
        return None, None, None

    nominatim = _reverse_geocode_nominatim(lat, lon)
    if nominatim is None:
        return district, None, None

    return district, nominatim["display"], nominatim["house_number"]


class SweepingCoordinator(DataUpdateCoordinator[SweepingData]):
    """Coordinator that polls GPS and queries Cambridge API."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._entity_id = entity_id
        self._last_lat: float | None = None
        self._last_lon: float | None = None
        self._cached_data: SweepingData = SweepingData()
        self._unsub_state_listener: callback | None = None

    async def async_setup(self) -> None:
        """Subscribe to device tracker state changes."""
        @callback
        def _async_on_state_change(event) -> None:
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            # Trigger refresh when tracker transitions from unavailable/unknown to a real state
            old_s = old_state.state if old_state else None
            if old_s in UNRESOLVED_STATES and new_state and new_state.state not in UNRESOLVED_STATES:
                self.hass.async_create_task(self.async_request_refresh())

        self._unsub_state_listener = async_track_state_change_event(
            self.hass, [self._entity_id], _async_on_state_change
        )

    async def async_shutdown(self) -> None:
        """Unsubscribe from state changes."""
        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None
        await super().async_shutdown()

    async def _async_update_data(self) -> SweepingData:
        """Fetch data from the device tracker and query the APIs."""
        state = self.hass.states.get(self._entity_id)
        if state is None:
            return SweepingData()

        lat = state.attributes.get("latitude")
        lon = state.attributes.get("longitude")
        if lat is None or lon is None:
            return SweepingData()

        if self._last_lat is not None and self._last_lon is not None:
            distance = _haversine_meters(self._last_lat, self._last_lon, lat, lon)
            if distance < MIN_MOVEMENT_METERS:
                self._refresh_next_date()
                return self._cached_data

        self._last_lat = lat
        self._last_lon = lon

        try:
            district, address, house_number = await self.hass.async_add_executor_job(
                _resolve_location, lat, lon
            )
        except requests.RequestException as err:
            raise UpdateFailed(f"Error querying geocoding APIs: {err}") from err

        if district is None:
            self._cached_data = SweepingData(in_cambridge=False)
            return self._cached_data

        if house_number is None:
            self._cached_data = SweepingData(
                district=district,
                in_cambridge=True,
                nearest_address=address,
            )
            return self._cached_data

        side = "odd" if house_number % 2 == 1 else "even"
        next_dt = get_next_sweep_date(district, house_number)

        self._cached_data = SweepingData(
            district=district,
            side=side,
            nearest_address=address,
            next_date=next_dt,
            schedule_expired=next_dt is None,
            in_cambridge=True,
        )
        return self._cached_data

    def _refresh_next_date(self) -> None:
        """Recompute next_date from cache (in case a day has passed)."""
        data = self._cached_data
        if not data.in_cambridge or not data.district or not data.nearest_address:
            return
        house_number = self._street_number_from_address(data.nearest_address)
        if house_number is None:
            return
        next_dt = get_next_sweep_date(data.district, house_number)
        data.next_date = next_dt
        data.schedule_expired = next_dt is None

    @staticmethod
    def _street_number_from_address(address: str | None) -> int | None:
        if not address:
            return None
        parts = address.strip().split()
        if parts and parts[0].isdigit():
            return int(parts[0])
        return None
