"""Tests for the location lookups."""

from __future__ import annotations

from urllib.parse import parse_qs

from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest

from custom_components.cambridge_street_sweeping import api
from custom_components.cambridge_street_sweeping.const import (
    CENTERLINE_URL,
    CLEANING_DISTRICTS_URL,
    MASTER_ADDRESS_LIST_URL,
    NOMINATIM_URL,
)

LAT = 42.3771
LON = -71.105

# East-west street; north of it is "left" of the centerline direction.
CENTERLINE = {
    "features": [
        {
            "attributes": {"Street": "Trowbridge St"},
            "geometry": {"paths": [[[-71.11, 42.377], [-71.10, 42.377]]]},
        }
    ]
}

# North side odd numbers, south side even numbers.
ADDRESSES = {
    "features": [
        {
            "attributes": {
                "StNm": "117",
                "Full_Addr": "117 Trowbridge St",
                "lat": 42.3772,
                "lon": -71.105,
            }
        },
        {
            "attributes": {
                "StNm": "121-123",
                "Full_Addr": "121-123 Trowbridge St",
                "lat": 42.3772,
                "lon": -71.104,
            }
        },
        {
            "attributes": {
                "StNm": "118",
                "Full_Addr": "118 Trowbridge St",
                "lat": 42.3768,
                "lon": -71.105,
            }
        },
    ]
}


def _nominatim(address):
    return {"address": address}


async def test_reverse_geocode_without_house_number_keeps_road(hass, aioclient_mock):
    aioclient_mock.get(
        NOMINATIM_URL, json=_nominatim({"road": "Trowbridge Street", "city": "Cambridge"})
    )
    result = await api.reverse_geocode_nominatim(async_get_clientsession(hass), LAT, LON)
    assert result == {
        "house_number": None,
        "road": "Trowbridge Street",
        "display": "Trowbridge Street",
    }


async def test_reverse_geocode_with_house_number(hass, aioclient_mock):
    aioclient_mock.get(
        NOMINATIM_URL,
        json=_nominatim(
            {"road": "Trowbridge Street", "city": "Cambridge", "house_number": "76;78"}
        ),
    )
    result = await api.reverse_geocode_nominatim(async_get_clientsession(hass), LAT, LON)
    assert result["house_number"] == 76
    assert result["display"] == "76 Trowbridge Street"
    assert aioclient_mock.mock_calls[0][3]["User-Agent"].startswith("HA-CambridgeStreetCleaning/")


@pytest.mark.parametrize(
    "address",
    [{"road": "Main Street", "city": "Boston"}, {"city": "Cambridge", "house_number": "5"}],
)
async def test_reverse_geocode_not_cambridge_or_no_road(hass, aioclient_mock, address):
    aioclient_mock.get(NOMINATIM_URL, json=_nominatim(address))
    assert await api.reverse_geocode_nominatim(async_get_clientsession(hass), LAT, LON) is None


async def test_refine_side_uses_majority_parity_of_target_side(hass, aioclient_mock):
    aioclient_mock.get(CENTERLINE_URL, json=CENTERLINE)
    aioclient_mock.get(MASTER_ADDRESS_LIST_URL, json=ADDRESSES)
    result = await api.refine_side_of_street(
        async_get_clientsession(hass), LAT, LON, "Trowbridge Street"
    )
    assert result == {"display": "117 Trowbridge St", "side": "odd"}


async def test_refine_side_escapes_quotes_in_where_clause(hass, aioclient_mock):
    centerline = {
        "features": [
            {
                "attributes": {"Street": "Msgr O'Brien Hwy"},
                "geometry": {"paths": [[[-71.11, 42.377], [-71.10, 42.377]]]},
            }
        ]
    }
    aioclient_mock.get(CENTERLINE_URL, json=centerline)
    aioclient_mock.get(MASTER_ADDRESS_LIST_URL, json={"features": []})
    await api.refine_side_of_street(async_get_clientsession(hass), LAT, LON, "Msgr O'Brien Hwy")
    url = aioclient_mock.mock_calls[1][1]
    assert parse_qs(url.query_string)["where"] == ["StName = 'Msgr O''Brien Hwy'"]


async def test_refine_side_returns_none_on_http_error(hass, aioclient_mock):
    aioclient_mock.get(CENTERLINE_URL, status=500)
    assert (
        await api.refine_side_of_street(async_get_clientsession(hass), LAT, LON, "Trowbridge St")
        is None
    )


async def test_resolve_location_prefers_refined_side(hass, aioclient_mock):
    """The refined side wins even if the nominatim house number disagrees."""
    aioclient_mock.get(
        CLEANING_DISTRICTS_URL, json={"features": [{"attributes": {"District": "F"}}]}
    )
    aioclient_mock.get(
        NOMINATIM_URL,
        json=_nominatim({"road": "Trowbridge Street", "city": "Cambridge", "house_number": "118"}),
    )
    aioclient_mock.get(CENTERLINE_URL, json=CENTERLINE)
    aioclient_mock.get(MASTER_ADDRESS_LIST_URL, json=ADDRESSES)
    result = await api.resolve_location(async_get_clientsession(hass), LAT, LON)
    assert result == api.ResolvedLocation("F", "117 Trowbridge St", "odd")


async def test_resolve_location_road_only_when_refine_fails(hass, aioclient_mock):
    aioclient_mock.get(
        CLEANING_DISTRICTS_URL, json={"features": [{"attributes": {"District": "F"}}]}
    )
    aioclient_mock.get(
        NOMINATIM_URL, json=_nominatim({"road": "Trowbridge Street", "city": "Cambridge"})
    )
    aioclient_mock.get(CENTERLINE_URL, json={"features": []})
    result = await api.resolve_location(async_get_clientsession(hass), LAT, LON)
    assert result == api.ResolvedLocation("F", "Trowbridge Street", None)


async def test_resolve_location_outside_cambridge(hass, aioclient_mock):
    aioclient_mock.get(CLEANING_DISTRICTS_URL, json={"features": []})
    assert await api.resolve_location(async_get_clientsession(hass), LAT, LON) is None
