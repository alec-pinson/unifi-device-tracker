from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_AWAY_DELAY,
    CONF_HOME_DELAY,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_TRACKED_MACS,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DEFAULT_AWAY_DELAY,
    DEFAULT_HOME_DELAY,
    DOMAIN,
)
from .coordinator import UnifiApiClient

_LOGGER = logging.getLogger(__name__)


def _client_label(client: dict) -> str:
    alias = (client.get("name") or "").strip()
    hostname = (client.get("hostname") or "").strip()
    mac = (client.get("mac") or "").lower()
    if alias and hostname:
        return f"{alias} ({hostname}, {mac})"
    if alias:
        return f"{alias} ({mac})"
    if hostname:
        return f"{hostname} ({mac})"
    return mac


class UnifiDeviceTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._clients: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api = UnifiApiClient(
                host=user_input[CONF_HOST],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                verify_ssl=user_input.get(CONF_VERIFY_SSL, False),
            )
            try:
                await api.async_login()
                self._clients = await api.async_get_clients()
            except ConfigEntryAuthFailed:
                errors["base"] = "invalid_auth"
            except HomeAssistantError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"
            finally:
                await api.async_close()

            if not errors:
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()
                self._credentials = user_input
                return await self.async_step_select_devices()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_VERIFY_SSL, default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_select_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            tracked = [m.lower() for m in user_input.get(CONF_TRACKED_MACS, [])]
            return self.async_create_entry(
                title=self._credentials[CONF_HOST],
                data=self._credentials,
                options={CONF_TRACKED_MACS: tracked},
            )

        option_by_mac: dict[str, SelectOptionDict] = {}
        for c in self._clients:
            mac = (c.get("mac") or "").lower()
            if not mac:
                continue
            option_by_mac[mac] = SelectOptionDict(value=mac, label=_client_label(c))
        options = sorted(option_by_mac.values(), key=lambda o: o["label"].lower())

        return self.async_show_form(
            step_id="select_devices",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TRACKED_MACS): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return UnifiDeviceTrackerOptionsFlow(config_entry)


class UnifiDeviceTrackerOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._clients: list[dict] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            tracked = [m.lower() for m in user_input.get(CONF_TRACKED_MACS, [])]
            return self.async_create_entry(data={
                CONF_TRACKED_MACS: tracked,
                CONF_AWAY_DELAY: user_input.get(CONF_AWAY_DELAY, DEFAULT_AWAY_DELAY),
                CONF_HOME_DELAY: user_input.get(CONF_HOME_DELAY, DEFAULT_HOME_DELAY),
            })

        api = UnifiApiClient(
            host=self._config_entry.data[CONF_HOST],
            username=self._config_entry.data[CONF_USERNAME],
            password=self._config_entry.data[CONF_PASSWORD],
            verify_ssl=self._config_entry.data.get(CONF_VERIFY_SSL, False),
        )
        try:
            await api.async_login()
            self._clients = await api.async_get_clients()
        except Exception:
            _LOGGER.exception("Failed to fetch clients for options flow")
            self._clients = []
        finally:
            await api.async_close()

        currently_tracked = [
            m.lower() for m in self._config_entry.options.get(CONF_TRACKED_MACS, [])
        ]
        current_away_delay = self._config_entry.options.get(CONF_AWAY_DELAY, DEFAULT_AWAY_DELAY)
        current_home_delay = self._config_entry.options.get(CONF_HOME_DELAY, DEFAULT_HOME_DELAY)

        option_by_mac: dict[str, SelectOptionDict] = {}
        for c in self._clients:
            mac = (c.get("mac") or "").lower()
            if not mac:
                continue
            option_by_mac[mac] = SelectOptionDict(value=mac, label=_client_label(c))

        # Ensure currently tracked MACs that aren't currently connected still
        # appear as selectable options — otherwise the selector rejects the
        # default value and the user can't save the form.
        offline_macs: set[str] = set()
        for mac in currently_tracked:
            if mac not in option_by_mac:
                option_by_mac[mac] = SelectOptionDict(value=mac, label=f"{mac} (offline)")
                offline_macs.add(mac)

        options = sorted(
            option_by_mac.values(),
            key=lambda o: (o["value"] in offline_macs, o["label"].lower()),
        )

        _delay_selector = NumberSelector(
            NumberSelectorConfig(min=0, max=3600, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AWAY_DELAY, default=current_away_delay): _delay_selector,
                    vol.Required(CONF_HOME_DELAY, default=current_home_delay): _delay_selector,
                    vol.Required(
                        CONF_TRACKED_MACS, default=currently_tracked
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )
