"""Config flow for Cambridge Street Sweeping."""

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers import selector

from .const import CONF_DEVICE_TRACKER, DOMAIN


class CambridgeStreetSweepingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cambridge Street Sweeping."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial step."""
        if user_input is not None:
            entity_id = user_input[CONF_DEVICE_TRACKER]
            await self.async_set_unique_id(entity_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Street Sweeping ({entity_id})",
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_TRACKER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="device_tracker")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
