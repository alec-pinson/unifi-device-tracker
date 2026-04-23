from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import UnifiAuthExpired, UnifiDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def _async_fetch_wlans(coordinator: UnifiDataUpdateCoordinator) -> list[dict]:
    try:
        return await coordinator.api.async_get_wlans()
    except UnifiAuthExpired:
        await coordinator.api.async_login()
        return await coordinator.api.async_get_wlans()


def _ssid_unique_id(entry: ConfigEntry, ssid: str) -> str:
    return f"unifi_ssid_{entry.entry_id}_{ssid}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UnifiDataUpdateCoordinator = entry.runtime_data
    ent_reg = er.async_get(hass)

    # Migrate legacy SSID unique_ids that didn't include the entry_id (these
    # would collide across multiple controllers configured against the same
    # SSID name).
    legacy_prefix = "unifi_ssid_"
    new_prefix = f"unifi_ssid_{entry.entry_id}_"
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        uid = ent.unique_id
        if uid.startswith(legacy_prefix) and not uid.startswith(new_prefix):
            ssid = uid[len(legacy_prefix):]
            ent_reg.async_update_entity(ent.entity_id, new_unique_id=new_prefix + ssid)

    known_ssids: set[str] = set()

    try:
        wlans = await _async_fetch_wlans(coordinator)
        configured_ssids = {w["name"] for w in wlans if w.get("name")}
    except Exception:
        _LOGGER.warning("Failed to fetch WLAN list; falling back to client-based discovery")
        configured_ssids = set()

    if configured_ssids:
        known_ssids.update(configured_ssids)
        async_add_entities(UnifiSsidSensor(coordinator, entry, ssid) for ssid in configured_ssids)

    @callback
    def _async_add_new_ssids() -> None:
        ssids = {c["essid"] for c in (coordinator.data or {}).values() if c.get("essid")}
        new_ssids = ssids - known_ssids
        if new_ssids:
            known_ssids.update(new_ssids)
            async_add_entities(UnifiSsidSensor(coordinator, entry, ssid) for ssid in new_ssids)

    _async_add_new_ssids()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_ssids))


class UnifiSsidSensor(CoordinatorEntity[UnifiDataUpdateCoordinator], SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "clients"
    _attr_icon = "mdi:wifi"

    def __init__(
        self,
        coordinator: UnifiDataUpdateCoordinator,
        entry: ConfigEntry,
        ssid: str,
    ) -> None:
        super().__init__(coordinator)
        self._ssid = ssid
        self._attr_unique_id = _ssid_unique_id(entry, ssid)
        self._attr_name = f"{ssid} Clients"

    @property
    def native_value(self) -> int:
        return sum(
            1 for c in (self.coordinator.data or {}).values()
            if c.get("essid") == self._ssid
        )
