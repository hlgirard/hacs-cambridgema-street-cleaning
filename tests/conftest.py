"""Shared fixtures."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cambridge_street_sweeping.const import CONF_DEVICE_TRACKER, DOMAIN

TRACKER = "device_tracker.car"
LAT = 42.3771
LON = -71.105


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in all tests."""
    return


@pytest.fixture
def tracker(hass):
    """A device tracker with a GPS position in Cambridge."""
    hass.states.async_set(
        TRACKER, "not_home", {"latitude": LAT, "longitude": LON, "friendly_name": "Car"}
    )
    return TRACKER


@pytest.fixture
def config_entry(hass) -> MockConfigEntry:
    """A config entry for the tracker."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Street Cleaning (Car)",
        unique_id=TRACKER,
        data={CONF_DEVICE_TRACKER: TRACKER},
    )
    entry.add_to_hass(hass)
    return entry
