from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_TRACKED_MACS
from .coordinator import UnifiDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.DEVICE_TRACKER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    tracked_macs = {m.lower() for m in entry.options.get(CONF_TRACKED_MACS, [])}
    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        uid = entity_entry.unique_id
        prefix = "unifi_device_tracker_"
        if uid.startswith(prefix):
            mac_flat = uid[len(prefix):]
            mac = ":".join(mac_flat[i:i+2] for i in range(0, 12, 2))
            if mac not in tracked_macs:
                entity_registry.async_remove(entity_entry.entity_id)

    coordinator = UnifiDataUpdateCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await coordinator.api.async_close()
        raise
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_update_options_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_start_websocket()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop_websocket()
        await entry.runtime_data.api.async_close()
    return unloaded


async def async_update_options_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
