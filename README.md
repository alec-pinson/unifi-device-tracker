# UniFi Device Tracker

A lightweight Home Assistant custom integration to track specific UniFi network clients as `device_tracker` entities. Designed as a minimal alternative to the official HA UniFi integration — no extra dependencies, no UNMS/Network Application required.

## Features

- Tracks selected UniFi clients as `home`/`not_home` device tracker entities
- Polls every 30 seconds via the UniFi OS local API
- Configurable via the Home Assistant UI (no YAML required)
- Add/remove tracked devices via the integration options without restarting HA
- Exposes extra attributes: IP address, hostname, last seen, SSID, signal strength

## Requirements

- Home Assistant 2026.3 or later
- UniFi OS gateway (e.g. Cloud Gateway Fibre, Dream Machine, UDM Pro)
- A local UniFi OS user with read access

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alec-pinson&repository=unifi-device-tracker&category=integration)

Or manually:

1. Open HACS → Integrations → three-dot menu → **Custom repositories**
2. Add this repository URL and select category **Integration**
3. Search for **UniFi Device Tracker** and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/unifi_device_tracker/` into your HA `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **UniFi Device Tracker**
3. Enter your UniFi OS host (e.g. `https://192.168.1.1`), username, and password
4. Select which clients you want to track from the live device list
5. Entities will appear as `device_tracker.<hostname>`

> **Note:** SSL verification is disabled by default since most home UniFi setups use a self-signed certificate. Enable it if you have a valid cert.

## Options

After setup, click **Configure** on the integration to update the list of tracked devices. The options flow re-fetches the live client list so any newly joined devices will appear.

## How It Works

- Authenticates against the UniFi OS local API (`/api/auth/login`)
- Polls `/proxy/network/api/s/default/stat/sta` every 30 seconds — this endpoint returns only **currently connected** clients
- A missing MAC in the response means the device is `not_home`
- On session expiry (HTTP 401), the integration automatically re-authenticates and retries

## Entities

Each tracked device creates a `device_tracker` entity with:

| Attribute | Description |
|---|---|
| `state` | `home` if connected, `not_home` if not |
| `source_type` | `router` |
| `ip` | Current IP address |
| `hostname` | Device hostname |
| `last_seen` | Unix timestamp of last seen |
| `essid` | SSID (Wi-Fi clients only) |
| `signal` | Signal strength in dBm (Wi-Fi clients only) |
