# RTLAMR WebSocket Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/alex-savin/hassio-integration-rtlamr.svg)](https://github.com/alex-savin/hassio-integration-rtlamr/releases)
[![License](https://img.shields.io/github/license/alex-savin/hassio-integration-rtlamr.svg)](LICENSE)

Home Assistant custom integration for receiving utility meter readings (gas, water, electric) from the RTLAMR WebSocket add-on via local push.

## Prerequisites

This integration requires the **[RTLAMR WebSocket Add-on](https://github.com/alex-savin/hassio-apps/tree/main/rtlamr-ws)** to be installed and running.

The add-on uses an RTL-SDR dongle to receive wireless meter transmissions, decodes them using rtlamr, and exposes the readings via a local WebSocket. This integration then connects to that WebSocket to create Home Assistant sensor entities.

### Add-on Installation

1. Add the add-on repository to Home Assistant:
   - Go to **Settings → Add-ons → Add-on Store**
   - Click the three dots (⋮) in the top right → **Repositories**
   - Add: `https://github.com/alex-savin/hassio-apps`
2. Find and install **RTLAMR WebSocket**
3. Configure the add-on with your meter IDs
4. Start the add-on
5. Note the WebSocket URL (typically `ws://homeassistant.local:8080/ws` or `ws://localhost:8080/ws`)

For detailed add-on configuration, see the [add-on documentation](https://github.com/alex-savin/hassio-apps/tree/main/rtlamr-ws).

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alex-savin&repository=hassio-integration-rtlamr&category=integration)

1. Open HACS in Home Assistant
2. Click "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/alex-savin/hassio-integration-rtlamr`
6. Select "Integration" as the category
7. Click "Add"
8. Search for "RTLAMR WebSocket" and install it
9. Restart Home Assistant

### Manual Installation

Copy the `custom_components/rtlamr_ws` folder to your Home Assistant `config/custom_components/` directory.

```
config/
└── custom_components/
    └── rtlamr_ws/
        ├── __init__.py
        ├── config_flow.py
        ├── const.py
        ├── manifest.json
        ├── sensor.py
        ├── strings.json
        └── translations/
            ├── de.json
            ├── en.json
            ├── es.json
            └── fr.json
```

## Configuration

1. Restart Home Assistant
2. Go to **Settings → Devices & Services → Add Integration**
3. Search for **RTLAMR WebSocket**
4. Enter the WebSocket URL (default: `ws://homeassistant.local:8080/ws`)

## Features

- Automatic sensor discovery for configured meters
- State restoration across restarts
- Full support for `device_class`, `state_class`, `unit_of_measurement`
- Multi-language support (English, Spanish, French, German)
- Local push updates (no cloud dependency)

## Entities

Sensors are automatically created for each meter detected:

| Entity | Description |
|--------|-------------|
| `sensor.meter_<id>` | Current meter reading value |

Each sensor includes attributes such as meter type, last update timestamp, and unit of measurement.

## Automation Examples

### Notify on high water usage

```yaml
alias: High water usage alert
trigger:
  - platform: numeric_state
    entity_id: sensor.meter_12345678
    above: 100
    for: "01:00:00"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "High Water Usage"
      message: "Water meter reading is unusually high: {{ states('sensor.meter_12345678') }}"
```

### Log daily gas consumption

```yaml
alias: Daily gas reading log
trigger:
  - platform: time
    at: "23:59:00"
action:
  - service: logbook.log
    data:
      name: "Gas Meter"
      message: "Daily reading: {{ states('sensor.meter_87654321') }} cubic feet"
```

## Troubleshooting

- **Sensors not appearing**: Ensure the RTLAMR WebSocket add-on is running and the WebSocket URL is correct.
- **Connection errors**: Check that the add-on is reachable from Home Assistant (try `ws://localhost:8080/ws` if running on the same host).
- **No readings**: Verify your RTL-SDR dongle is connected and the add-on logs show meter detections.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
