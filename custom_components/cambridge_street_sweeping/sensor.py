"""Sensor platform for Cambridge Street Cleaning."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CambridgeStreetCleaningConfigEntry, StreetCleaningCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CambridgeStreetCleaningConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor from a config entry."""
    async_add_entities([CambridgeStreetCleaningSensor(entry.runtime_data)])


class CambridgeStreetCleaningSensor(CoordinatorEntity[StreetCleaningCoordinator], SensorEntity):
    """Sensor showing the next street cleaning date."""

    _attr_has_entity_name = True
    _attr_translation_key = "next_cleaning"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: StreetCleaningCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        # Unique ID kept from 0.2.x so existing entity IDs are preserved.
        self._attr_unique_id = f"{entry.entry_id}_next_sweep"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="City of Cambridge",
            name=entry.title,
        )

    @property
    def native_value(self) -> date | None:
        """Return the next cleaning date, or None."""
        return self.coordinator.data.next_date

    @property
    def icon(self) -> str | None:
        """Show a warning icon when the schedule has run out."""
        if self.coordinator.data.schedule_expired:
            return "mdi:alert"
        # Fall back to the icon translation in icons.json.
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        data = self.coordinator.data
        attrs: dict[str, Any] = {
            "district": data.district,
            "side": data.side,
            "nearest_address": data.nearest_address,
            "in_cambridge": data.in_cambridge,
            "schedule_expired": data.schedule_expired,
        }
        if data.next_date:
            # Attribute name kept from 0.2.x for template compatibility.
            attrs["next_sweep_formatted"] = data.next_date.strftime("%A, %B %d, %Y")
        return attrs
