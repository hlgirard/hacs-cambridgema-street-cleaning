"""Sensor platform for Cambridge Street Sweeping."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_TRACKER, DOMAIN
from .coordinator import SweepingCoordinator, SweepingData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor from a config entry."""
    entity_id = entry.data[CONF_DEVICE_TRACKER]
    coordinator = SweepingCoordinator(hass, entity_id)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()
    async_add_entities([CambridgeSweepingSensor(coordinator, entry)])


class CambridgeSweepingSensor(CoordinatorEntity[SweepingCoordinator], SensorEntity):
    """Sensor showing next street sweeping date."""

    _attr_has_entity_name = True
    _attr_name = "Next Street Sweeping"
    _attr_icon = "mdi:broom"

    def __init__(self, coordinator: SweepingCoordinator, entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_next_sweep"

    @property
    def native_value(self) -> str | None:
        """Return the next sweeping date as ISO string, or None."""
        data: SweepingData = self.coordinator.data
        if not data.in_cambridge:
            return None
        if data.schedule_expired:
            return "schedule_expired"
        if data.next_date:
            return data.next_date.isoformat()
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return additional attributes."""
        data: SweepingData = self.coordinator.data
        attrs: dict[str, str | None] = {
            "district": data.district,
            "side": data.side,
            "nearest_address": data.nearest_address,
            "in_cambridge": str(data.in_cambridge),
        }
        if data.next_date:
            attrs["next_sweep_formatted"] = data.next_date.strftime("%A, %B %d, %Y")
        if data.schedule_expired:
            attrs["warning"] = (
                f"All {DOMAIN} schedule dates have passed. Update the schedule data."
            )
        return attrs
