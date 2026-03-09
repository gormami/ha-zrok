# ha-zrok — Home Assistant zrok Integration

Expose your Home Assistant instance (and other local services) via a [zrok](https://zrok.io) public tunnel, managed entirely from within HA.

---

## Features

- **Auto-downloads** the correct zrok binary for your architecture at startup
- **UI-only config flow** — no YAML required
- **Ephemeral or Reserved** share URLs, configurable per entry
- **Secure token storage** via HA's credential store
- **Sensor entities** for tunnel URL and status
- **Lovelace card** showing live tunnel URL with conditional status alerts
- **HACS compatible**

---

## Installation via HACS

1. In HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/gormami/ha-zrok` as an **Integration**
3. Install **zrok Tunnel** and restart Home Assistant

## Manual Installation

```bash
cp -r custom_components/zrok /config/custom_components/zrok
```
Restart Home Assistant.

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **zrok**
3. Enter your [zrok account token](https://docs.zrok.io/docs/getting-started/)
4. Choose share mode (Ephemeral / Reserved) and HA port
5. Finish — the tunnel starts automatically

---

## Adding the Lovelace Card

Open your dashboard in **Edit mode → Add Card → Manual**, then paste the contents of `lovelace_card.yaml`.

---

## Adding Extra Services

Currently, extra services (e.g. Zigbee2MQTT on port 8080) can be added by setting `extra_services` in the config entry options. A dedicated UI step for this is planned.

---

## File Structure

```
ha-zrok/
├── custom_components/
│   └── zrok/
│       ├── __init__.py          # Integration setup & teardown
│       ├── manifest.json        # HACS/HA metadata
│       ├── const.py             # All constants
│       ├── config_flow.py       # UI config & options flow
│       ├── binary_manager.py    # Auto-download zrok binary
│       ├── tunnel_manager.py    # zrok process lifecycle
│       ├── sensor.py            # Sensor platform
│       └── strings.json         # UI strings / translations
├── hacs.json
├── lovelace_card.yaml
└── README.md
```

---

## Security Notes

- Your zrok token is stored in HA's encrypted credential store
- The zrok binary is downloaded from the official [OpenZiti GitHub releases](https://github.com/openziti/zrok/releases)
- Only `localhost` services are exposed — no LAN-wide exposure
- Use a **Reserved** share token for a stable, predictable URL