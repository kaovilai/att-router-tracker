# AT&T Router Device Tracker for Home Assistant

This custom integration tracks devices connected to your AT&T router by scraping the device list from the router's web interface.

## Features

- **Smart Presence Detection**: Distinguishes between always-home devices (smart TVs, thermostats) and tracked devices (phones, laptops)
- **Device Tracking**: Creates device_tracker entities only for non-always-home devices
- **Presence Sensor**: Detects if someone is home based on tracked devices being online
- **Connection Details**: Shows WiFi signal strength, connection type, IP addresses
- **Summary Sensors**: 
  - Online devices count (excluding always-home devices)
  - Total known devices count
  - Presence detection (home/away)
- **Configurable Options**: Mark devices as always-home through the integration options
- Updates every 30 seconds

## Installation

1. Copy the `att_router_tracker` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration
4. Search for "AT&T Router Device Tracker"

## Configuration

### Initial Setup
You'll need two pieces of information:

#### 1. Router IP Address
Usually `192.168.1.254` for AT&T routers

#### 2. Session ID
To get your session ID:
1. Open your browser and log into your router at http://192.168.1.254
2. Enter your Device Access Code (found on the router label)
3. Once logged in, open your browser's Developer Tools (F12)
4. Go to the Application/Storage tab
5. Find Cookies → http://192.168.1.254
6. Copy the value of the `SessionID` cookie

### Configuring Always-Home Devices
After initial setup:
1. Go to Settings → Devices & Services
2. Find your AT&T Router integration
3. Click "Configure"
4. Select devices that are always at home (smart home devices, TVs, etc.)
5. These devices won't be tracked for presence detection

## Entities Created

### Device Trackers
- One entity per **tracked device** (excludes always-home devices)
- Shows as "home" when online, "not_home" when offline
- Attributes include:
  - MAC address
  - IP address (if assigned)
  - Connection type (WiFi/Ethernet)
  - Signal strength (for WiFi devices)
  - Last activity time
  - Connection speed

### Sensors
- **Online Devices**: Count of currently online tracked devices (excluding always-home)
- **Total Devices**: Total number of all known devices
- **Presence**: Shows "home" when tracked devices are online, "away" when only always-home devices are online

## Example Automations

### Presence-based automation
```yaml
automation:
  - alias: "Someone Arrived Home"
    trigger:
      - platform: state
        entity_id: sensor.att_router_presence
        from: "away"
        to: "home"
    action:
      - service: light.turn_on
        target:
          entity_id: light.entrance
      - service: climate.set_preset_mode
        target:
          entity_id: climate.thermostat
        data:
          preset_mode: "home"
```

### Away mode automation
```yaml
automation:
  - alias: "Everyone Left Home"
    trigger:
      - platform: state
        entity_id: sensor.att_router_presence
        from: "home"
        to: "away"
        for: "00:05:00"  # Wait 5 minutes to avoid false triggers
    action:
      - service: light.turn_off
        target:
          entity_id: group.all_lights
      - service: climate.set_preset_mode
        target:
          entity_id: climate.thermostat
        data:
          preset_mode: "away"
```

### Guest detection
```yaml
automation:
  - alias: "Guest Arrived"
    trigger:
      - platform: state
        entity_id: sensor.att_router_online_devices
    condition:
      - condition: template
        value_template: >
          {{ trigger.to_state.state | int > trigger.from_state.state | int 
             and trigger.to_state.state | int > 1 }}
    action:
      - service: notify.mobile_app
        data:
          message: "Guest device connected to network"
```

## Troubleshooting

- **Cannot connect**: Verify your session ID is still valid. Session IDs expire after an unknown duration (likely a few hours to days). You'll need to log in again and get a new session ID.
- **Devices not updating**: Check that your router is accessible at the configured IP address.
- **Missing devices**: Some devices may only appear after they've been active on the network.
- **Presence not working correctly**: Make sure you've marked all your always-home devices in the integration options.

## Notes

- **Session Management**: The session ID will expire periodically. When this happens, the integration will stop updating and you'll need to reconfigure with a new session ID.
- **Always-Home Devices**: Smart home devices (TVs, thermostats, smart speakers) should be marked as always-home to get accurate presence detection.
- **Device Names**: Names are taken from the router's device list. You can rename device entities in Home Assistant for better identification.
- **Privacy**: All data stays local - no cloud services are used.

## How Presence Detection Works

The integration distinguishes between two types of devices:
1. **Always-Home Devices**: Devices that stay at home (smart TVs, thermostats, etc.)
2. **Tracked Devices**: Mobile devices that indicate someone's presence (phones, tablets, laptops)

When any tracked device is online, the presence sensor shows "home". When only always-home devices are online, it shows "away". This prevents false presence detection from smart home devices while accurately tracking when people are actually home.