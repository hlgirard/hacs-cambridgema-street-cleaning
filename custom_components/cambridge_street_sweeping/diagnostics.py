"""Diagnostics support for Cambridge Street Cleaning."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import CambridgeStreetCleaningConfigEntry

TO_REDACT = {"nearest_address"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CambridgeStreetCleaningConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    The tracker's coordinates are never stored, and the nearest address is
    redacted so the vehicle's location is not shared.
    """
    coordinator = entry.runtime_data
    data = asdict(coordinator.data) if coordinator.data else None
    if data and data["next_date"]:
        data["next_date"] = data["next_date"].isoformat()
    return {
        "entry": {"title": entry.title, "data": dict(entry.data)},
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(data, TO_REDACT) if data else None,
    }
