"""Tests for setup, the sensor, the repair issue and diagnostics."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.cambridge_street_sweeping.api import ResolvedLocation
from custom_components.cambridge_street_sweeping.const import DOMAIN, ISSUE_SCHEDULE_EXPIRED
from custom_components.cambridge_street_sweeping.diagnostics import (
    async_get_config_entry_diagnostics,
)

RESOLVE = "custom_components.cambridge_street_sweeping.coordinator.resolve_location"
ENTITY_ID = "sensor.street_cleaning_car_next_street_cleaning"


@pytest.fixture
def resolve():
    with patch(
        RESOLVE,
        new=AsyncMock(return_value=ResolvedLocation("A", "117 Main St", "odd")),
    ) as mock:
        yield mock


async def _setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensor_state_and_attributes(hass, freezer, tracker, config_entry, resolve):
    freezer.move_to("2026-06-01 12:00:00")
    await _setup(hass, config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state.state == "2026-06-03"
    assert state.attributes["district"] == "A"
    assert state.attributes["side"] == "odd"
    assert state.attributes["nearest_address"] == "117 Main St"
    assert state.attributes["in_cambridge"] is True
    assert state.attributes["schedule_expired"] is False
    assert state.attributes["next_sweep_formatted"] == "Wednesday, June 03, 2026"
    assert state.attributes["friendly_name"] == "Street Cleaning (Car) Next street cleaning"

    entity = er.async_get(hass).async_get(ENTITY_ID)
    assert entity.unique_id == f"{config_entry.entry_id}_next_sweep"
    device = dr.async_get(hass).async_get(entity.device_id)
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.manufacturer == "City of Cambridge"


async def test_existing_entity_id_is_preserved(hass, freezer, tracker, config_entry, resolve):
    freezer.move_to("2026-06-01 12:00:00")
    er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{config_entry.entry_id}_next_sweep",
        config_entry=config_entry,
        suggested_object_id="next_street_sweeping",
    )
    await _setup(hass, config_entry)
    assert hass.states.get("sensor.next_street_sweeping").state == "2026-06-03"


async def test_stationary_refresh_recomputes_date(hass, freezer, tracker, config_entry, resolve):
    freezer.move_to("2026-06-01 12:00:00")
    await _setup(hass, config_entry)
    assert hass.states.get(ENTITY_ID).state == "2026-06-03"

    freezer.move_to("2026-06-04 12:00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "2026-07-01"
    assert resolve.await_count == 1  # Not moved: no new API lookup.


async def test_unknown_side_has_no_date(hass, freezer, tracker, config_entry):
    freezer.move_to("2026-06-01 12:00:00")
    with patch(RESOLVE, new=AsyncMock(return_value=ResolvedLocation("A", "Main St", None))):
        await _setup(hass, config_entry)
    state = hass.states.get(ENTITY_ID)
    assert state.state == "unknown"
    assert state.attributes["in_cambridge"] is True
    assert state.attributes["schedule_expired"] is False


async def test_outside_cambridge(hass, tracker, config_entry):
    with patch(RESOLVE, new=AsyncMock(return_value=None)):
        await _setup(hass, config_entry)
    state = hass.states.get(ENTITY_ID)
    assert state.state == "unknown"
    assert state.attributes["in_cambridge"] is False


async def test_expired_schedule_raises_repair_issue(hass, freezer, tracker, config_entry, resolve):
    freezer.move_to("2026-12-20 12:00:00")
    await _setup(hass, config_entry)

    state = hass.states.get(ENTITY_ID)
    assert state.state == "unknown"
    assert state.attributes["schedule_expired"] is True
    assert state.attributes["icon"] == "mdi:alert"
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_SCHEDULE_EXPIRED)


async def test_api_error_retries_setup(hass, tracker, config_entry):
    with patch(RESOLVE, new=AsyncMock(side_effect=aiohttp.ClientError("boom"))):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_tracker_recovery_triggers_refresh(hass, freezer, config_entry, resolve):
    freezer.move_to("2026-06-01 12:00:00")
    hass.states.async_set("device_tracker.car", "unavailable")
    await _setup(hass, config_entry)
    assert resolve.await_count == 0

    hass.states.async_set(
        "device_tracker.car", "not_home", {"latitude": 42.3771, "longitude": -71.105}
    )
    freezer.tick(timedelta(seconds=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert resolve.await_count == 1


async def test_unload(hass, tracker, config_entry, resolve):
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redacts_address(hass, freezer, tracker, config_entry, resolve):
    freezer.move_to("2026-06-01 12:00:00")
    await _setup(hass, config_entry)
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["data"]["nearest_address"] == "**REDACTED**"
    assert diag["data"]["next_date"] == "2026-06-03"
    assert diag["data"]["district"] == "A"
