"""Tests for the config flow."""

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.cambridge_street_sweeping.const import CONF_DEVICE_TRACKER, DOMAIN


async def test_user_flow_creates_entry(hass, tracker):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    with patch("custom_components.cambridge_street_sweeping.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_TRACKER: tracker}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Street Cleaning (Car)"
    assert result["data"] == {CONF_DEVICE_TRACKER: tracker}
    assert result["result"].unique_id == tracker


async def test_duplicate_aborts(hass, tracker, config_entry):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_TRACKER: tracker}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_changes_tracker(hass, tracker, config_entry):
    hass.states.async_set("device_tracker.bike", "home", {"friendly_name": "Bike"})
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    with patch("custom_components.cambridge_street_sweeping.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_TRACKER: "device_tracker.bike"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_DEVICE_TRACKER] == "device_tracker.bike"
    assert config_entry.unique_id == "device_tracker.bike"
    assert config_entry.title == "Street Cleaning (Bike)"
