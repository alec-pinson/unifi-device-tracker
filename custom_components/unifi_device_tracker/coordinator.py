from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    UNIFI_CLIENTS_PATH,
    UNIFI_LOGIN_PATH,
    UNIFI_WLANS_PATH,
)

_LOGGER = logging.getLogger(__name__)


class UnifiApiClient:
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool) -> None:
        self._host = host.rstrip("/")
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl
        self._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True)
        )

    async def async_login(self) -> None:
        url = f"{self._host}{UNIFI_LOGIN_PATH}"
        payload = {"username": self._username, "password": self._password, "remember": False}
        try:
            async with self._session.post(
                url,
                json=payload,
                ssl=self._verify_ssl,
                allow_redirects=False,
            ) as resp:
                if resp.status == 401:
                    raise ConfigEntryAuthFailed("Invalid credentials")
                if resp.status not in (200, 302):
                    raise HomeAssistantError(f"Login failed with status {resp.status}")
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"Cannot connect to UniFi: {err}") from err

    async def async_get_clients(self) -> list[dict]:
        url = f"{self._host}{UNIFI_CLIENTS_PATH}"
        try:
            async with self._session.get(url, ssl=self._verify_ssl) as resp:
                if resp.status == 401:
                    raise PermissionError("Unauthorized — session expired")
                resp.raise_for_status()
                body = await resp.json()
                return body.get("data", [])
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"Error fetching clients: {err}") from err

    async def async_get_wlans(self) -> list[dict]:
        url = f"{self._host}{UNIFI_WLANS_PATH}"
        try:
            async with self._session.get(url, ssl=self._verify_ssl) as resp:
                if resp.status == 401:
                    raise PermissionError("Unauthorized — session expired")
                resp.raise_for_status()
                body = await resp.json()
                return body.get("data", [])
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"Error fetching WLANs: {err}") from err

    async def async_close(self) -> None:
        await self._session.close()


class UnifiDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.api = UnifiApiClient(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
        )
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_setup(self) -> None:
        try:
            await self.api.async_login()
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise ConfigEntryNotReady(f"Unable to connect to UniFi: {err}") from err

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            clients = await self.api.async_get_clients()
        except PermissionError:
            _LOGGER.debug("Session expired, re-logging in")
            try:
                await self.api.async_login()
                clients = await self.api.async_get_clients()
            except Exception as err:
                raise UpdateFailed(f"Re-login failed: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching UniFi clients: {err}") from err

        return {c["mac"].lower(): c for c in clients if "mac" in c}
