"""Lookups against the Cambridge GIS layers and Nominatim."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
import logging
import math
from typing import Any

import aiohttp

from .const import (
    CENTERLINE_URL,
    CLEANING_DISTRICTS_URL,
    MASTER_ADDRESS_LIST_URL,
    MAX_ADDRESS_DISTANCE_METERS,
    NOMINATIM_URL,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)
from .schedule import side_for_number

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

_SUFFIX_MAP = {
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


@dataclass(frozen=True)
class ResolvedLocation:
    """Result of resolving a GPS position inside Cambridge."""

    district: str
    address: str | None = None
    side: str | None = None


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance between two GPS points in meters."""
    r = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _get_json(
    session: aiohttp.ClientSession,
    url: str,
    params: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    async with session.get(url, params=params, headers=headers, timeout=_TIMEOUT) as resp:
        resp.raise_for_status()
        # ArcGIS sometimes answers with text/plain; parse regardless.
        return await resp.json(content_type=None)


async def reverse_geocode_nominatim(
    session: aiohttp.ClientSession, lat: float, lon: float
) -> dict[str, Any] | None:
    """Reverse geocode via Nominatim to get street address and house number."""
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "addressdetails": 1,
        "zoom": 18,
    }
    data = await _get_json(session, NOMINATIM_URL, params, {"User-Agent": USER_AGENT})

    address = data.get("address", {})
    if "cambridge" not in address.get("city", "").lower():
        return None

    road = address.get("road", "")
    if not road:
        return None

    # Nominatim may return "76;78" for interpolated addresses — take the first
    house_number = address.get("house_number", "").split(";")[0].strip()

    if not house_number.isdigit():
        # No usable house number (e.g. parking lot): keep the road so the
        # side of street can still be refined from the Cambridge layers.
        return {"house_number": None, "road": road, "display": road}

    return {
        "house_number": int(house_number),
        "road": road,
        "display": f"{house_number} {road}",
    }


async def query_cleaning_district(
    session: aiohttp.ClientSession, lat: float, lon: float
) -> str | None:
    """Query the Cambridge cleaning districts layer for the district at a point."""
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "District",
        "returnGeometry": "false",
        "f": "json",
        "inSR": 4326,
    }
    data = await _get_json(session, CLEANING_DISTRICTS_URL, params)
    features = data.get("features", [])
    if not features:
        return None
    return features[0]["attributes"].get("District")


def clean_street_name(name: str | None) -> str:
    """Normalize a street name so Nominatim and city names can be compared."""
    if not name:
        return ""
    parts = name.strip().split()
    if not parts:
        return ""
    last_lower = parts[-1].lower()
    if last_lower in _SUFFIX_MAP:
        parts[-1] = _SUFFIX_MAP[last_lower]
    return " ".join(parts)


def arcgis_quote(value: str) -> str:
    """Quote a string literal for an ArcGIS SQL where clause."""
    return "'" + value.replace("'", "''") + "'"


def _distance_point_to_line_segment(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def determine_side_of_centerline(
    px: float, py: float, paths: list[list[list[float]]]
) -> str | None:
    """Return "left" or "right" of the closest centerline segment, or None.

    ``paths`` holds every polyline of the centerline: the city's features are
    often multi-part, and the part nearest the point may not be the first.
    """
    best_segment = None
    min_dist = float("inf")
    for path in paths:
        for (x1, y1), (x2, y2) in pairwise(path):
            dist = _distance_point_to_line_segment(px, py, x1, y1, x2, y2)
            if dist < min_dist:
                min_dist = dist
                best_segment = (x1, y1, x2, y2)

    if best_segment is None:
        return None

    x1, y1, x2, y2 = best_segment
    cross_product = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
    return "left" if cross_product > 0 else "right"


async def refine_side_of_street(
    session: aiohttp.ClientSession, lat: float, lon: float, road: str
) -> dict[str, Any] | None:
    """Refine side of street using the Cambridge centerline and address layers.

    Returns {"display", "side"} or None if it can't be determined.
    """
    cleaned_road = clean_street_name(road).lower()

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
        data = await _get_json(session, CENTERLINE_URL, params)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.warning("Error querying Centerline Web layer: %s", err)
        return None

    matching = [
        feat
        for feat in data.get("features", [])
        if clean_street_name(feat.get("attributes", {}).get("Street")).lower() == cleaned_road
    ]
    if not matching:
        _LOGGER.debug("No matching centerline found for road '%s'", road)
        return None

    cl_name = matching[0]["attributes"]["Street"]
    paths = [
        path
        for feat in matching
        for path in feat.get("geometry", {}).get("paths", [])
        if len(path) >= 2
    ]
    if not paths:
        return None

    target_side = determine_side_of_centerline(lon, lat, paths)
    if target_side is None:
        return None

    addr_params = {
        "where": f"StName = {arcgis_quote(cl_name)}",
        "outFields": "StNm,StName,Full_Addr,Sweep_District,lat,lon",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "json",
    }
    try:
        addr_data = await _get_json(session, MASTER_ADDRESS_LIST_URL, addr_params)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.warning("Error querying Master Address List: %s", err)
        return None

    odds = 0
    evens = 0
    candidates: list[tuple[float, str | None]] = []

    for feat in addr_data.get("features", []):
        attrs = feat.get("attributes", {})
        geometry = feat.get("geometry", {})
        a_lon = attrs.get("lon") or geometry.get("x")
        a_lat = attrs.get("lat") or geometry.get("y")
        if a_lon is None or a_lat is None:
            continue
        distance = haversine_meters(lat, lon, a_lat, a_lon)
        # The centerline only covers the stretch near the car; farther
        # addresses would be compared against extrapolated segments.
        if distance > MAX_ADDRESS_DISTANCE_METERS:
            continue
        if determine_side_of_centerline(a_lon, a_lat, paths) != target_side:
            continue

        st_num = str(attrs.get("StNm") or "")
        clean_num = "".join(c for c in st_num.split("-")[0] if c.isdigit())
        if not clean_num:
            continue
        if side_for_number(int(clean_num)) == "odd":
            odds += 1
        else:
            evens += 1
        candidates.append((distance, attrs.get("Full_Addr")))

    if not candidates:
        return None

    _, nearest_addr = min(candidates, key=lambda c: c[0])
    return {
        "display": nearest_addr,
        "side": "odd" if odds > evens else "even",
    }


async def resolve_location(
    session: aiohttp.ClientSession, lat: float, lon: float
) -> ResolvedLocation | None:
    """Resolve GPS to district, display address and side of street.

    Returns None if the point is not in a Cambridge cleaning district. Side is
    None when it could not be determined.
    """
    district = await query_cleaning_district(session, lat, lon)
    if district is None:
        return None

    nominatim = await reverse_geocode_nominatim(session, lat, lon)
    if nominatim is None:
        return ResolvedLocation(district=district)

    refined = await refine_side_of_street(session, lat, lon, nominatim["road"])
    if refined:
        return ResolvedLocation(
            district=district,
            address=refined["display"] or nominatim["display"],
            side=refined["side"],
        )

    house_number = nominatim["house_number"]
    return ResolvedLocation(
        district=district,
        address=nominatim["display"],
        side=side_for_number(house_number) if house_number is not None else None,
    )
