from __future__ import annotations

import asyncio
import contextlib
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DOMAIN,
    UNIFI_CLIENTS_PATH,
    UNIFI_LOGIN_PATH,
    UNIFI_WLANS_PATH,
    UNIFI_WS_PATH,
    WS_CONNECT_KEYS,
    WS_DISCONNECT_KEYS,
    WS_EVENT_EVENTS,
    WS_EVENT_STA_SYNC,
    WS_HEARTBEAT_INTERVAL,
    WS_RECONNECT_MAX_DELAY,
    WS_RECONNECT_MIN_DELAY,
)

_LOGGER = logging.getLogger(__name__)


class UnifiAuthExpired(Exception):
    """Raised when the UniFi session has expired and needs re-login."""


class UnifiApiClient:
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool) -> None:
        self._host = host.rstrip("/")
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl
        self._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            timeout=aiohttp.ClientTimeout(total=10),
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
                    raise UnifiAuthExpired("Unauthorized — session expired")
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
                    raise UnifiAuthExpired("Unauthorized — session expired")
                resp.raise_for_status()
                body = await resp.json()
                return body.get("data", [])
        except aiohttp.ClientError as err:
            raise HomeAssistantError(f"Error fetching WLANs: {err}") from err

    async def async_ws_connect(self) -> aiohttp.ClientWebSocketResponse:
        ws_url = self._host.replace("https://", "wss://").replace("http://", "ws://")
        return await self._session.ws_connect(
            f"{ws_url}{UNIFI_WS_PATH}",
            ssl=self._verify_ssl,
            heartbeat=WS_HEARTBEAT_INTERVAL,
        )

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
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
            config_entry=entry,
        )
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ws_task: asyncio.Task | None = None
        self._ws_connected: bool = False
        self._ws_reconnect_delay: float = WS_RECONNECT_MIN_DELAY

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
        except UnifiAuthExpired:
            _LOGGER.debug("Session expired, re-logging in")
            try:
                await self.api.async_login()
                clients = await self.api.async_get_clients()
            except ConfigEntryAuthFailed:
                raise
            except Exception as err:
                raise UpdateFailed(f"Re-login failed: {err}") from err
            # Close the WebSocket so the listener reconnects with the fresh
            # session cookie. Must NOT call async_stop_websocket() here — this
            # coroutine may itself be running inside the WS listener task
            # (via async_refresh() after reconnect), and cancelling the
            # current task while awaiting it would deadlock.
            if self._ws is not None and not self._ws.closed:
                with contextlib.suppress(Exception):
                    async with asyncio.timeout(1):
                        await self._ws.close()
        except Exception as err:
            raise UpdateFailed(f"Error fetching UniFi clients: {err}") from err

        return {c["mac"].lower(): c for c in clients if c.get("mac")}

    async def async_start_websocket(self) -> None:
        if self._ws_task is not None:
            return
        self._ws_task = self.hass.async_create_background_task(
            self._ws_listener(),
            name=f"{DOMAIN}_websocket",
        )

    async def async_stop_websocket(self) -> None:
        if self._ws_task is not None:
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            self._ws_task = None
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
            self._ws = None
        self._ws_connected = False

    async def _ws_listener(self) -> None:
        while True:
            try:
                try:
                    self._ws = await self.api.async_ws_connect()
                except Exception as err:
                    _LOGGER.debug("WebSocket connect failed: %s", err)
                    try:
                        await self.api.async_login()
                    except ConfigEntryAuthFailed:
                        _LOGGER.error(
                            "WebSocket re-login failed: invalid credentials, requesting reauth"
                        )
                        if self.config_entry is not None:
                            self.config_entry.async_start_reauth(self.hass)
                        return
                    except Exception as login_err:
                        _LOGGER.debug("WebSocket re-login failed: %s", login_err)
                    await self._ws_backoff()
                    continue

                _LOGGER.info("WebSocket connected to UniFi controller")
                self._ws_connected = True
                self._ws_reconnect_delay = WS_RECONNECT_MIN_DELAY

                # Re-fetch current client list to establish ground truth after
                # (re)connect — catches disconnect events missed while WS was down
                await self.async_refresh()

                await self._ws_receive_loop()

            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug("WebSocket error: %s", err)
            finally:
                self._ws_connected = False
                ws = self._ws
                self._ws = None
                # Shield close from cancellation propagating into the await,
                # otherwise the socket can be left half-open and leak fds
                # across entry reloads.
                if ws is not None and not ws.closed:
                    with contextlib.suppress(Exception):
                        await asyncio.shield(ws.close())

            _LOGGER.info("WebSocket disconnected, reconnecting")
            await self._ws_backoff()

    async def _ws_receive_loop(self) -> None:
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    self._process_ws_message(msg.json())
                except (ValueError, KeyError) as err:
                    _LOGGER.debug("Failed to parse WebSocket message: %s", err)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                _LOGGER.debug("WebSocket error: %s", self._ws.exception())
                break
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                break

    @callback
    def _process_ws_message(self, payload: dict) -> None:
        meta = payload.get("meta", {})
        message_type = meta.get("message", "")
        data_list = payload.get("data", [])

        if not data_list:
            return

        current_data = dict(self.data) if self.data else {}
        notify = False

        if message_type == WS_EVENT_STA_SYNC:
            for client in data_list:
                mac = (client.get("mac") or "").lower()
                if not mac:
                    continue
                if mac not in current_data:
                    _LOGGER.debug("Client connected via sta:sync: mac=%s", mac)
                    notify = True
                current_data[mac] = client

        elif message_type == WS_EVENT_EVENTS:
            for event in data_list:
                key = event.get("key") or ""
                mac = (event.get("user") or event.get("mac") or "").lower()
                if key in WS_CONNECT_KEYS:
                    # Don't add from the event payload — it's an event dict, not
                    # a client dict (no name/hostname/ip/essid). sta:sync
                    # follows on connect and provides the proper client record.
                    _LOGGER.debug("Client connect event: mac=%s key=%s", mac, key)
                elif key in WS_DISCONNECT_KEYS:
                    _LOGGER.debug("Client disconnected: mac=%s key=%s", mac, key)
                    if mac and mac in current_data:
                        del current_data[mac]
                        notify = True

        if notify:
            self.async_set_updated_data(current_data)
        else:
            self.data = current_data

    async def _ws_backoff(self) -> None:
        _LOGGER.debug("WebSocket reconnect in %s seconds", self._ws_reconnect_delay)
        await asyncio.sleep(self._ws_reconnect_delay)
        self._ws_reconnect_delay = min(
            self._ws_reconnect_delay * 2,
            WS_RECONNECT_MAX_DELAY,
        )
