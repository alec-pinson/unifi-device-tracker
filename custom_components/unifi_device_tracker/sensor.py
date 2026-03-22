from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import UnifiDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UnifiDataUpdateCoordinator = entry.runtime_data
    known_ssids: set[str] = set()

    try:
        wlans = await coordinator.api.async_get_wlans()
        configured_ssids = {w["name"] for w in wlans if w.get("name")}
    except Exception:
        _LOGGER.warning("Failed to fetch WLAN list; falling back to client-based discovery")
        configured_ssids = set()

    if configured_ssids:
        known_ssids.update(configured_ssids)
        async_add_entities(UnifiSsidSensor(coordinator, ssid) for ssid in configured_ssids)

    @callback
    def _async_add_new_ssids() -> None:
        ssids = {c["essid"] for c in coordinator.data.values() if c.get("essid")}
        new_ssids = ssids - known_ssids
        if new_ssids:
            known_ssids.update(new_ssids)
            async_add_entities(UnifiSsidSensor(coordinator, ssid) for ssid in new_ssids)

    _async_add_new_ssids()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_ssids))


class UnifiSsidSensor(CoordinatorEntity[UnifiDataUpdateCoordinator], SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "clients"
    _attr_icon = "mdi:wifi"

    def __init__(self, coordinator: UnifiDataUpdateCoordinator, ssid: str) -> None:
        super().__init__(coordinator)
        self._ssid = ssid
        self._attr_unique_id = f"unifi_ssid_{ssid}"
        self._attr_name = f"{ssid} Clients"

    @property
    def native_value(self) -> int:
        return sum(1 for c in self.coordinator.data.values() if c.get("essid") == self._ssid)
