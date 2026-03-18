# UniFi Device Tracker — Dev Notes

## Overview
Home Assistant custom integration (`unifi_device_tracker`) that tracks UniFi network clients as `device_tracker` entities. Polls the UniFi OS local API every 30 seconds.

## Test Environment
- Test HA runs on k3s, kubectl context: `pi-k8s-cluster`, namespace: `default`
- Test pod: `test-home-assistant-*` (deployment: `test-home-assistant`)
- Deploy command: `kubectl cp custom_components/unifi_device_tracker <pod>:/config/custom_components/unifi_device_tracker --context pi-k8s-cluster --namespace default`
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

## API Paths
- Login: `POST /api/auth/login`
- Clients: `GET /proxy/network/api/s/default/stat/sta`

## Structure
```
custom_components/unifi_device_tracker/
├── __init__.py          # setup/unload, options reload listener
├── manifest.json
├── const.py
├── coordinator.py       # UnifiApiClient + UnifiDataUpdateCoordinator
├── config_flow.py       # 2-step config flow + options flow
├── device_tracker.py    # CoordinatorEntity + ScannerEntity
├── strings.json
├── translations/en.json
└── brand/
    ├── icon.png
    └── icon@2x.png
```
