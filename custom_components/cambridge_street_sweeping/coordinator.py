"""Data update coordinator for Cambridge Street Cleaning."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import haversine_meters, resolve_location
from .const import (
    CONF_DEVICE_TRACKER,
    DOMAIN,
    ISSUE_SCHEDULE_EXPIRED,
    MIN_MOVEMENT_METERS,
    UPDATE_INTERVAL_MINUTES,
)
from .schedule import SCHEDULE_YEAR, get_next_cleaning_date

_LOGGER = logging.getLogger(__name__)

UNRESOLVED_STATES = {STATE_UNKNOWN, STATE_UNAVAILABLE, None}


@dataclass
class CleaningData:
    """Street cleaning lookup result."""

    district: str | None = None
    side: str | None = None
    nearest_address: str | None = None
    next_date: date | None = None
    schedule_expired: bool = False
    in_cambridge: bool = False


type CambridgeStreetCleaningConfigEntry = ConfigEntry[StreetCleaningCoordinator]


class StreetCleaningCoordinator(DataUpdateCoordinator[CleaningData]):
    """Coordinator that polls the tracker location and queries the city APIs."""

    config_entry: CambridgeStreetCleaningConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: CambridgeStreetCleaningConfigEntry
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self.tracker_entity_id: str = config_entry.data[CONF_DEVICE_TRACKER]
        self._session = async_get_clientsession(hass)
        self._last_lat: float | None = None
        self._last_lon: float | None = None
        self._cached_data = CleaningData()

    async def _async_setup(self) -> None:
        """Refresh as soon as the tracker comes back from unavailable/unknown."""

        @callback
        def _async_on_state_change(event: Event[EventStateChangedData]) -> None:
            old_state = event.data["old_state"]
            new_state = event.data["new_state"]
            old_s = old_state.state if old_state else None
            if (
                old_s in UNRESOLVED_STATES
                and new_state is not None
                and new_state.state not in UNRESOLVED_STATES
            ):
                self.hass.async_create_task(self.async_request_refresh())

        self.config_entry.async_on_unload(
            async_track_state_change_event(
                self.hass, [self.tracker_entity_id], _async_on_state_change
            )
        )

    async def _async_update_data(self) -> CleaningData:
        """Fetch the tracker location and query the APIs when it moved."""
        data = await self._async_fetch()
        self._update_expired_issue(data)
        return data

    async def _async_fetch(self) -> CleaningData:
        state = self.hass.states.get(self.tracker_entity_id)
        if state is None:
            return CleaningData()

        lat = state.attributes.get(ATTR_LATITUDE)
        lon = state.attributes.get(ATTR_LONGITUDE)
        if lat is None or lon is None:
            return CleaningData()

        if (
            self._last_lat is not None
            and self._last_lon is not None
            and haversine_meters(self._last_lat, self._last_lon, lat, lon) < MIN_MOVEMENT_METERS
        ):
            # Stationary: only recompute the date in case one has passed.
            self._cached_data = self._with_next_date(self._cached_data)
            return self._cached_data

        try:
            location = await resolve_location(self._session, lat, lon)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise UpdateFailed(f"Error querying location APIs: {err}") from err

        # Only remember the position once it was resolved successfully.
        self._last_lat = lat
        self._last_lon = lon

        if location is None:
            self._cached_data = CleaningData(in_cambridge=False)
        else:
            self._cached_data = self._with_next_date(
                CleaningData(
                    district=location.district,
                    side=location.side,
                    nearest_address=location.address,
                    in_cambridge=True,
                )
            )
        return self._cached_data

    @staticmethod
    def _with_next_date(data: CleaningData) -> CleaningData:
        """Return a copy of data with next_date recomputed for today."""
        if not data.in_cambridge or not data.district or not data.side:
            return data
        next_dt = get_next_cleaning_date(data.district, data.side)
        return replace(data, next_date=next_dt, schedule_expired=next_dt is None)

    def _update_expired_issue(self, data: CleaningData) -> None:
        if data.schedule_expired:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_SCHEDULE_EXPIRED,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_SCHEDULE_EXPIRED,
                translation_placeholders={"year": str(SCHEDULE_YEAR)},
            )
        elif data.next_date is not None:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_SCHEDULE_EXPIRED)
