from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AWAY_DELAY,
    CONF_HOME_DELAY,
    CONF_TRACKED_MACS,
    DEFAULT_AWAY_DELAY,
    DEFAULT_HOME_DELAY,
    DOMAIN,
    WS_DISCONNECT_SUPPRESSION_WINDOW,
)
from .coordinator import UnifiDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UnifiDataUpdateCoordinator = entry.runtime_data
    tracked_macs = [m.lower() for m in entry.options.get(CONF_TRACKED_MACS, [])]
    async_add_entities(
        UnifiDeviceTracker(coordinator, mac) for mac in tracked_macs
    )


class UnifiDeviceTracker(CoordinatorEntity[UnifiDataUpdateCoordinator], ScannerEntity):
    _attr_source_type = SourceType.ROUTER
    def __init__(self, coordinator: UnifiDataUpdateCoordinator, mac: str) -> None:
        super().__init__(coordinator)
        self._mac = mac.lower()
        self._attr_unique_id = f"unifi_device_tracker_{self._mac.replace(':', '')}"
        self._last_seen: datetime | None = None
        self._first_seen: datetime | None = None
        self._last_known_client: dict | None = None
        self._unsub_delay: Callable[[], None] | None = None

    @property
    def entity_registry_enabled_default(self) -> bool:
        return True

    @property
    def _client(self) -> dict | None:
        return self.coordinator.data.get(self._mac)

    @callback
    def _handle_coordinator_update(self) -> None:
        now = dt_util.utcnow()
        if self._client is not None:
            self._last_known_client = self._client
            # Re-arm home_delay grace only on a genuinely fresh connection —
            # not on a fast roam or brief drop within the suppression window,
            # otherwise a real WiFi handoff causes a visible flicker to Away.
            gap_too_long = (
                self._last_seen is not None
                and (now - self._last_seen).total_seconds() > WS_DISCONNECT_SUPPRESSION_WINDOW
            )
            if self._first_seen is None or gap_too_long:
                self._first_seen = now
            self._last_seen = now
        # Do not null _first_seen on disconnect: it survives brief gaps so
        # fast roams don't re-trigger home_delay. On a long-gap reconnect
        # the gap_too_long check above will re-arm it.
        #
        # Note: silent restores in the coordinator (reconnect within the
        # suppression window) deliberately do NOT call this method, so
        # _last_seen won't advance during those events. A pending away_delay
        # timer from the preceding disconnect may fire as a harmless no-op.
        self._schedule_delay_expiry()
        super()._handle_coordinator_update()

    @callback
    def _schedule_delay_expiry(self) -> None:
        if self._unsub_delay is not None:
            self._unsub_delay()
            self._unsub_delay = None

        options = self.coordinator.config_entry.options
        away_delay = options.get(CONF_AWAY_DELAY, DEFAULT_AWAY_DELAY)
        home_delay = options.get(CONF_HOME_DELAY, DEFAULT_HOME_DELAY)
        now = dt_util.utcnow()
        remaining: float | None = None

        if self._client is None:
            if away_delay > 0 and self._last_seen is not None:
                expiry = away_delay - (now - self._last_seen).total_seconds()
                if expiry > 0:
                    remaining = expiry
        else:
            if home_delay > 0 and self._first_seen is not None:
                expiry = home_delay - (now - self._first_seen).total_seconds()
                if expiry > 0:
                    remaining = expiry

        if remaining is not None:
            self._unsub_delay = async_call_later(
                self.hass, remaining + 0.1, self._delay_expired
            )

    @callback
    def _delay_expired(self, _now) -> None:
        self._unsub_delay = None
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_delay is not None:
            self._unsub_delay()
            self._unsub_delay = None
        await super().async_will_remove_from_hass()

    @property
    def is_connected(self) -> bool:
        options = self.coordinator.config_entry.options
        away_delay = options.get(CONF_AWAY_DELAY, DEFAULT_AWAY_DELAY)
        home_delay = options.get(CONF_HOME_DELAY, DEFAULT_HOME_DELAY)
        now = dt_util.utcnow()

        if self._client is not None:
            if home_delay > 0 and self._first_seen is not None:
                if (now - self._first_seen).total_seconds() < home_delay:
                    return False
            return True

        if away_delay > 0 and self._last_seen is not None:
            if (now - self._last_seen).total_seconds() < away_delay:
                return True
        return False

    @property
    def name(self) -> str:
        client = self._client or self._last_known_client
        if client:
            return client.get("name") or client.get("hostname") or self._mac
        return self._mac

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def hostname(self) -> str | None:
        client = self._client or self._last_known_client
        if client:
            return client.get("hostname") or client.get("name")
        return None

    @property
    def ip_address(self) -> str | None:
        client = self._client or self._last_known_client
        if client:
            return client.get("ip")
        return None

    @property
    def extra_state_attributes(self) -> dict:
        client = self._client or self._last_known_client
        if not client:
            return {}
        attrs = {}
        for key in ("ip", "hostname", "last_seen", "essid", "signal"):
            if key in client:
                attrs[key] = client[key]
        return attrs
