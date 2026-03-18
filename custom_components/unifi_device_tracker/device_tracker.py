from __future__ import annotations

import logging

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TRACKED_MACS, DOMAIN
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

    @property
    def _client(self) -> dict | None:
        return self.coordinator.data.get(self._mac)

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    @property
    def name(self) -> str:
        client = self._client
        if client:
            return client.get("hostname") or client.get("name") or self._mac
        return self._mac

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def hostname(self) -> str | None:
        client = self._client
        if client:
            return client.get("hostname") or client.get("name")
        return None

    @property
    def ip_address(self) -> str | None:
        client = self._client
        if client:
            return client.get("ip")
        return None

    @property
    def extra_state_attributes(self) -> dict:
        client = self._client
        if not client:
            return {}
        attrs = {}
        for key in ("ip", "hostname", "last_seen", "essid", "signal"):
            if key in client:
                attrs[key] = client[key]
        return attrs
