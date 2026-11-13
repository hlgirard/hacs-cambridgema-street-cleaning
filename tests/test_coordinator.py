"""Tests for location resolution in the coordinator."""

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(scope="module")
def coordinator():
    """Import coordinator with a minimal homeassistant stub."""
    names = [
        "homeassistant",
        "homeassistant.const",
        "homeassistant.core",
        "homeassistant.helpers",
        "homeassistant.helpers.event",
        "homeassistant.helpers.update_coordinator",
    ]
    for name in names:
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules["homeassistant.const"].STATE_UNAVAILABLE = "unavailable"
    sys.modules["homeassistant.const"].STATE_UNKNOWN = "unknown"
    sys.modules["homeassistant.core"].HomeAssistant = object
    sys.modules["homeassistant.core"].callback = lambda f: f
    sys.modules["homeassistant.helpers.event"].async_track_state_change_event = None

    class _Coordinator:
        def __class_getitem__(cls, item):
            return cls

    uc = sys.modules["homeassistant.helpers.update_coordinator"]
    uc.DataUpdateCoordinator = _Coordinator
    uc.UpdateFailed = Exception

    pkg = types.ModuleType("css")
    pkg.__path__ = [
        str(Path(__file__).parent.parent / "custom_components" / "cambridge_street_sweeping")
    ]
    sys.modules["css"] = pkg
    return importlib.import_module("css.coordinator")


def _nominatim_response(address):
    resp = MagicMock()
    resp.json.return_value = {"address": address}
    return resp


def test_reverse_geocode_without_house_number_keeps_road(coordinator):
    resp = _nominatim_response({"road": "Trowbridge Street", "city": "Cambridge"})
    with patch.object(coordinator.requests, "get", return_value=resp):
        result = coordinator._reverse_geocode_nominatim(42.377, -71.109)
    assert result == {
        "house_number": None,
        "road": "Trowbridge Street",
        "display": "Trowbridge Street",
    }


def test_reverse_geocode_with_house_number(coordinator):
    resp = _nominatim_response(
        {"road": "Trowbridge Street", "city": "Cambridge", "house_number": "76;78"}
    )
    with patch.object(coordinator.requests, "get", return_value=resp):
        result = coordinator._reverse_geocode_nominatim(42.377, -71.109)
    assert result["house_number"] == 76
    assert result["display"] == "76 Trowbridge Street"


@pytest.mark.parametrize(
    "address",
    [
        {"road": "Main Street", "city": "Boston"},
        {"city": "Cambridge", "house_number": "5"},
    ],
)
def test_reverse_geocode_not_cambridge_or_no_road(coordinator, address):
    with patch.object(coordinator.requests, "get", return_value=_nominatim_response(address)):
        assert coordinator._reverse_geocode_nominatim(42.377, -71.109) is None


def test_resolve_location_uses_refined_side_when_no_house_number(coordinator):
    nominatim = {"house_number": None, "road": "Trowbridge Street", "display": "Trowbridge Street"}
    refined = {"road": "Trowbridge St", "house_number": 118, "display": "118 Trowbridge St", "side": "even"}
    with (
        patch.object(coordinator, "_query_sweep_district", return_value="F"),
        patch.object(coordinator, "_reverse_geocode_nominatim", return_value=nominatim),
        patch.object(coordinator, "_refine_side_of_street", return_value=refined),
    ):
        assert coordinator._resolve_location(42.377, -71.109) == ("F", "118 Trowbridge St", 118)


def test_resolve_location_road_only_when_refine_fails(coordinator):
    nominatim = {"house_number": None, "road": "Trowbridge Street", "display": "Trowbridge Street"}
    with (
        patch.object(coordinator, "_query_sweep_district", return_value="F"),
        patch.object(coordinator, "_reverse_geocode_nominatim", return_value=nominatim),
        patch.object(coordinator, "_refine_side_of_street", return_value=None),
    ):
        assert coordinator._resolve_location(42.377, -71.109) == ("F", "Trowbridge Street", None)
