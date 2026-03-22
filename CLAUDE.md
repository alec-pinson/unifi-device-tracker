# UniFi Device Tracker — Dev Notes

## Overview
Home Assistant custom integration (`unifi_device_tracker`) that tracks UniFi network clients as `device_tracker` entities. Uses a WebSocket connection to the UniFi OS controller for real-time push-based presence detection, with a single REST call on startup for initial state.

## Test Environment
- Test HA runs on k3s, kubectl context: `pi-k8s-cluster`, namespace: `default`
- Test pod: `test-home-assistant-*` (deployment: `test-home-assistant`)
- Deploy command: `kubectl exec <pod> -- rm -rf /config/custom_components/unifi_device_tracker && kubectl cp custom_components/unifi_device_tracker <pod>:/config/custom_components/ --context pi-k8s-cluster --namespace default`
- Restart: `kubectl rollout restart deployment/test-home-assistant --context pi-k8s-cluster --namespace default`

## Icons
- Icons live in `brand/` subdirectory (`icon.png`, `icon@2x.png`)
- Local `brand/` serving requires **HA 2026.3+** — prior versions only resolve icons from `brands.home-assistant.io` CDN (i.e. the `home-assistant/brands` GitHub repo)
- UniFi has no dark icon variants in the brands repo — only `icon.png` and `icon@2x.png`

## Key Implementation Details
- `aiohttp.CookieJar(unsafe=True)` is mandatory — without it, cookies are silently dropped for IP-address hosts and every request returns 401
- Login accepts HTTP 200 and 302 — some UniFi OS firmware redirects after auth
- Always lowercase MACs — normalize in coordinator output and config flow options
- `stat/sta` returns only currently connected clients — missing MAC = `not_home`
- Uses `entry.runtime_data` (modern HA 2024+ pattern, not `hass.data[DOMAIN]`)
- `aiohttp` is bundled with HA — never add it to `requirements` in `manifest.json`
- Entity name priority: UniFi `name` (alias) → `hostname` → MAC
- `BaseTrackerEntity` overrides `entity_registry_enabled_default` as a property returning `False` — must override the **property** in the entity class (not just set `_attr_entity_registry_enabled_default`) to ensure entities are enabled on first registration
- Away delay and home delay are stored in `entry.options` and read on coordinator/entity init — entry reload applies changes
- Stale entities (unticked MACs) are removed from the entity registry in `async_setup_entry` before platforms are set up

## WebSocket Details
- Endpoint: `wss://<host>/proxy/network/wss/s/default/events`
- Auth: cookie-based, shares session with REST client (`CookieJar(unsafe=True)`)
- Heartbeat: aiohttp `heartbeat=25` (auto ping/pong, catches silent drops)
- Reconnection: exponential backoff 5s → 300s, reset on successful connect
- `sta:sync` messages: presence in data = connected (no `state` field — it's always `None` for connected clients)
- `events` messages: disconnect keys are `EVT_WU_Disconnected` / `EVT_WG_Disconnected` (CamelCase with `EVT_` prefix, NOT `wu.disconnected`)
- `events` messages: `user` field contains the client MAC (not `mac` field)
- Connect detection: `sta:sync` adds/updates client in coordinator data
- Disconnect detection: `events` with disconnect keys removes client from coordinator data
- Only calls `async_set_updated_data()` when data actually changes (avoids update spam from frequent `sta:sync`)

## API Paths
- Login: `POST /api/auth/login`
- Clients: `GET /proxy/network/api/s/default/stat/sta`
- WLANs: `GET /proxy/network/api/s/default/rest/wlanconf`
- WebSocket: `wss://<host>/proxy/network/wss/s/default/events`

## Structure
```
custom_components/unifi_device_tracker/
├── __init__.py          # setup/unload, options reload listener
├── manifest.json
├── const.py
├── coordinator.py       # UnifiApiClient + UnifiDataUpdateCoordinator + WebSocket
├── config_flow.py       # 2-step config flow + options flow
├── device_tracker.py    # CoordinatorEntity + ScannerEntity
├── sensor.py            # SSID client count sensors
├── strings.json
├── translations/en.json
└── brand/
    ├── icon.png
    └── icon@2x.png
```
