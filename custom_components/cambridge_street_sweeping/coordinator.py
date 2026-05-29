"""Data update coordinator for Cambridge Street Sweeping."""

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta

import requests

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    MASTER_ADDRESS_URL,
    MIN_MOVEMENT_METERS,
    SPATIAL_QUERY_RADIUS_METERS,
    UPDATE_INTERVAL_MINUTES,
    get_next_sweep_date,
)

_LOGGER = logging.getLogger(__name__)


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


def _query_nearest_address(lat: float, lon: float) -> dict | None:
    """Query Cambridge Master Address List for the nearest address to a GPS point."""
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": SPATIAL_QUERY_RADIUS_METERS,
        "units": "esriSRUnit_Meter",
        "inSR": 4326,
        "outFields": "Full_Addr,Sweep_District,StNm",
        "returnGeometry": "false",
        "resultRecordCount": 1,
        "f": "json",
    }
    resp = requests.get(MASTER_ADDRESS_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    features = data.get("features", [])
    if not features:
        return None
    return features[0]["attributes"]


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

    async def _async_update_data(self) -> SweepingData:
        """Fetch data from the device tracker and query the API."""
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
                # Re-compute next_date in case a day has passed, but skip the API call
                if self._cached_data.in_cambridge and self._cached_data.district:
                    street_num = self._street_number_from_address(
                        self._cached_data.nearest_address
                    )
                    if street_num is not None:
                        next_dt = get_next_sweep_date(
                            self._cached_data.district, street_num
                        )
                        self._cached_data.next_date = next_dt
                        self._cached_data.schedule_expired = next_dt is None
                return self._cached_data

        self._last_lat = lat
        self._last_lon = lon

        try:
            result = await self.hass.async_add_executor_job(
                _query_nearest_address, lat, lon
            )
        except requests.RequestException as err:
            raise UpdateFailed(f"Error querying Cambridge API: {err}") from err

        if result is None:
            self._cached_data = SweepingData(in_cambridge=False)
            return self._cached_data

        district = result.get("Sweep_District")
        full_addr = result.get("Full_Addr", "")
        street_num = self._street_number_from_address(full_addr)

        if not district or street_num is None:
            self._cached_data = SweepingData(
                in_cambridge=True, nearest_address=full_addr
            )
            return self._cached_data

        side = "odd" if street_num % 2 == 1 else "even"
        next_dt = get_next_sweep_date(district, street_num)

        self._cached_data = SweepingData(
            district=district,
            side=side,
            nearest_address=full_addr,
            next_date=next_dt,
            schedule_expired=next_dt is None,
            in_cambridge=True,
        )
        return self._cached_data

    @staticmethod
    def _street_number_from_address(address: str | None) -> int | None:
        if not address:
            return None
        parts = address.strip().split()
        if parts and parts[0].isdigit():
            return int(parts[0])
        return None
