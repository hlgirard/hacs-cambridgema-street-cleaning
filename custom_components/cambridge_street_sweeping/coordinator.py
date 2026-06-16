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
    CENTERLINE_URL,
    DOMAIN,
    MASTER_ADDRESS_LIST_URL,
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


def _clean_street_name(name: str | None) -> str:
    if not name:
        return ""
    parts = name.strip().split()
    if not parts:
        return ""
    suffix_map = {
        "road": "Rd",
        "rd": "Rd",
        "street": "St",
        "st": "St",
        "avenue": "Ave",
        "ave": "Ave",
        "terrace": "Ter",
        "ter": "Ter",
        "place": "Pl",
        "pl": "Pl",
        "court": "Ct",
        "ct": "Ct",
        "parkway": "Pkwy",
        "pkwy": "Pkwy",
        "square": "Sq",
        "sq": "Sq",
    }
    last_lower = parts[-1].lower()
    if last_lower in suffix_map:
        parts[-1] = suffix_map[last_lower]
    return " ".join(parts)


def _distance_point_to_line_segment(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> tuple[float, float]:
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1), 0.0
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    return math.hypot(px - closest_x, py - closest_y), t


def _determine_side_of_centerline(px: float, py: float, path: list[list[float]]) -> str:
    min_dist = float("inf")
    best_segment = None
    for i in range(len(path) - 1):
        x1, y1 = path[i]
        x2, y2 = path[i + 1]
        dist, _ = _distance_point_to_line_segment(px, py, x1, y1, x2, y2)
        if dist < min_dist:
            min_dist = dist
            best_segment = (x1, y1, x2, y2)

    if best_segment is None:
        return "unknown"

    x1, y1, x2, y2 = best_segment
    dx = x2 - x1
    dy = y2 - y1
    vx = px - x1
    vy = py - y1
    cross_product = dx * vy - dy * vx
    return "left" if cross_product > 0 else "right"


def _refine_side_of_street(lat: float, lon: float, nominatim: dict) -> dict | None:
    """Refine side of street using Cambridge Centerline and Master Address layers."""
    road = nominatim.get("road")
    if not road:
        return None

    cleaned_road = _clean_street_name(road).lower()

    # Query Centerline Web layer by geometry (within 50 meters)
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": 50,
        "units": "esriSRUnit_Meter",
        "inSR": 4326,
        "outSR": 4326,
        "outFields": "Street,OBJECTID",
        "returnGeometry": "true",
        "f": "json",
    }
    try:
        resp = requests.get(CENTERLINE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as err:
        _LOGGER.warning("Error querying Centerline Web layer: %s", err)
        return None

    features = data.get("features", [])
    matching_cl = None
    for feat in features:
        street_name = feat.get("attributes", {}).get("Street")
        if _clean_street_name(street_name).lower() == cleaned_road:
            matching_cl = feat
            break

    if not matching_cl:
        _LOGGER.info("No matching centerline found for road '%s'", road)
        return None

    cl_name = matching_cl.get("attributes", {}).get("Street")
    paths = matching_cl.get("geometry", {}).get("paths", [])
    if not paths or not paths[0]:
        return None
    path = paths[0]

    # Determine which side of centerline target is on
    target_side = _determine_side_of_centerline(lon, lat, path)
    if target_side == "unknown":
        return None

    # Query Master Address List for addresses on this street
    addr_params = {
        "where": f"StName = '{cl_name}'",
        "outFields": "StNm,StName,Full_Addr,Sweep_District,lat,lon",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "json",
    }
    try:
        resp = requests.get(MASTER_ADDRESS_LIST_URL, params=addr_params, timeout=10)
        resp.raise_for_status()
        addr_data = resp.json()
    except Exception as err:
        _LOGGER.warning("Error querying Master Address List: %s", err)
        return None

    addr_features = addr_data.get("features", [])
    if not addr_features:
        return None

    left_odds = 0
    left_evens = 0
    right_odds = 0
    right_evens = 0

    left_addresses = []
    right_addresses = []

    for feat in addr_features:
        attrs = feat.get("attributes", {})
        a_lon = attrs.get("lon") or feat.get("geometry", {}).get("x")
        a_lat = attrs.get("lat") or feat.get("geometry", {}).get("y")
        if a_lon is None or a_lat is None:
            continue
        a_side = _determine_side_of_centerline(a_lon, a_lat, path)
        if a_side == "unknown":
            continue

        st_num_str = attrs.get("StNm", "")
        # Parse house number
        clean_num = "".join(c for c in st_num_str.split("-")[0] if c.isdigit())
        if not clean_num:
            continue
        num = int(clean_num)
        is_odd = (num % 2 == 1)

        dist = _haversine_meters(lat, lon, a_lat, a_lon)
        addr_info = {
            "num": num,
            "addr": attrs.get("Full_Addr"),
            "lat": a_lat,
            "lon": a_lon,
            "dist": dist,
            "is_odd": is_odd,
        }

        if a_side == "left":
            left_addresses.append(addr_info)
            if is_odd:
                left_odds += 1
            else:
                left_evens += 1
        elif a_side == "right":
            right_addresses.append(addr_info)
            if is_odd:
                right_odds += 1
            else:
                right_evens += 1

    # Determine parity of the target side
    if target_side == "left":
        target_parity = "odd" if left_odds > left_evens else "even"
        candidates = left_addresses
    else:
        target_parity = "odd" if right_odds > right_evens else "even"
        candidates = right_addresses

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["dist"])
    nearest_match = candidates[0]

    return {
        "road": cl_name,
        "house_number": nearest_match["num"],
        "display": nearest_match["addr"],
        "side": target_parity,
    }


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

    refined = _refine_side_of_street(lat, lon, nominatim)
    if refined:
        return district, refined["display"], refined["house_number"]

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
