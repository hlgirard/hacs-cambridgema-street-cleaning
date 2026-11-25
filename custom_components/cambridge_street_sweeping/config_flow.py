"""Config flow for Cambridge Street Cleaning."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.helpers import selector
import voluptuous as vol

from .const import CONF_DEVICE_TRACKER, DOMAIN


def _schema(default: str | None = None) -> vol.Schema:
    key = (
        vol.Required(CONF_DEVICE_TRACKER, default=default)
        if default
        else vol.Required(CONF_DEVICE_TRACKER)
    )
    return vol.Schema(
        {key: selector.EntitySelector(selector.EntitySelectorConfig(domain="device_tracker"))}
    )


class CambridgeStreetCleaningConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cambridge Street Cleaning."""

    VERSION = 1

    def _title(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        name = state.attributes.get(ATTR_FRIENDLY_NAME) if state else None
        return f"Street Cleaning ({name or entity_id})"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            entity_id = user_input[CONF_DEVICE_TRACKER]
            await self.async_set_unique_id(entity_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._title(entity_id), data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema())

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the tracked device."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            entity_id = user_input[CONF_DEVICE_TRACKER]
            await self.async_set_unique_id(entity_id)
            if entity_id != entry.unique_id:
                self._abort_if_unique_id_configured()
            return self.async_update_reload_and_abort(
                entry,
                unique_id=entity_id,
                title=self._title(entity_id),
                data_updates=user_input,
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(entry.data[CONF_DEVICE_TRACKER]),
        )
