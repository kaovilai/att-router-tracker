"""Sensor platform for AT&T Router."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ALWAYS_HOME_DEVICES,
    CONF_PRESENCE_DETECTION,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor for AT&T Router."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    sensors = [
        ATTRouterOnlineDevicesSensor(coordinator, entry),
        ATTRouterTotalDevicesSensor(coordinator, entry.data[CONF_HOST]),
    ]
    
    # Add presence sensor if enabled
    if entry.data.get(CONF_PRESENCE_DETECTION, True):
        sensors.append(ATTRouterPresenceSensor(coordinator, entry))
    
    async_add_entities(sensors)


class ATTRouterOnlineDevicesSensor(CoordinatorEntity, SensorEntity):
    """Sensor for number of online devices."""
    
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:devices"
    
    def __init__(self, coordinator, entry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._host = entry.data[CONF_HOST]
        self._attr_unique_id = f"att_router_{self._host}_online_devices"
        self._attr_name = f"AT&T Router Online Devices"
    
    @property
    def native_value(self) -> int:
        """Return the number of online devices."""
        if not self.coordinator.data:
            return 0
        
        always_home = self._entry.data.get(CONF_ALWAYS_HOME_DEVICES, [])
        
        return sum(
            1 for mac, device in self.coordinator.data.items()
            if device.get("is_online", False) and mac not in always_home
        )
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}
        
        always_home = self._entry.data.get(CONF_ALWAYS_HOME_DEVICES, [])
        
        online_devices = [
            device.get("name", device.get("mac", "Unknown"))
            for mac, device in self.coordinator.data.items()
            if device.get("is_online", False) and mac not in always_home
        ]
        
        always_home_online = [
            self.coordinator.data[mac].get("name", mac)
            for mac in always_home
            if mac in self.coordinator.data and self.coordinator.data[mac].get("is_online", False)
        ]
        
        return {
            "online_devices": online_devices,
            "always_home_devices_online": always_home_online,
            "count": len(online_devices),
        }


class ATTRouterTotalDevicesSensor(CoordinatorEntity, SensorEntity):
    """Sensor for total number of known devices."""
    
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:counter"
    
    def __init__(self, coordinator, host):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._host = host
        self._attr_unique_id = f"att_router_{host}_total_devices"
        self._attr_name = f"AT&T Router Total Devices"
    
    @property
    def native_value(self) -> int:
        """Return the total number of devices."""
        if not self.coordinator.data:
            return 0
        
        return len(self.coordinator.data)
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}
        
        device_list = [
            {
                "name": device.get("name", "Unknown"),
                "mac": device.get("mac_formatted", device.get("mac", "Unknown")),
                "status": device.get("status", "unknown"),
                "ip": device.get("ip"),
            }
            for device in self.coordinator.data.values()
        ]
        
        # Sort by status (online first) then by name
        device_list.sort(
            key=lambda x: (x["status"] != "on", x["name"].lower())
        )
        
        return {
            "devices": device_list,
            "online_count": sum(1 for d in device_list if d["status"] == "on"),
            "offline_count": sum(1 for d in device_list if d["status"] == "off"),
        }


class ATTRouterPresenceSensor(CoordinatorEntity, SensorEntity):
    """Sensor for presence detection based on non-always-home devices."""
    
    _attr_icon = "mdi:home-account"
    
    def __init__(self, coordinator, entry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._host = entry.data[CONF_HOST]
        self._attr_unique_id = f"att_router_{self._host}_presence"
        self._attr_name = f"AT&T Router Presence"
    
    @property
    def native_value(self) -> str:
        """Return presence state."""
        if not self.coordinator.data:
            return "unknown"
        
        always_home = self._entry.data.get(CONF_ALWAYS_HOME_DEVICES, [])
        
        # Count non-always-home devices that are online
        tracked_online = sum(
            1 for mac, device in self.coordinator.data.items()
            if device.get("is_online", False) and mac not in always_home
        )
        
        if tracked_online > 0:
            return "home"
        else:
            return "away"
    
    @property
    def icon(self) -> str:
        """Return the icon based on presence."""
        if self.native_value == "home":
            return "mdi:home-account"
        else:
            return "mdi:home-outline"
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}
        
        always_home = self._entry.data.get(CONF_ALWAYS_HOME_DEVICES, [])
        
        # Get tracked devices (non-always-home)
        tracked_online = []
        tracked_offline = []
        always_home_online = []
        always_home_offline = []
        
        for mac, device in self.coordinator.data.items():
            name = device.get("name", mac)
            if mac in always_home:
                if device.get("is_online", False):
                    always_home_online.append(name)
                else:
                    always_home_offline.append(name)
            else:
                if device.get("is_online", False):
                    tracked_online.append(name)
                else:
                    tracked_offline.append(name)
        
        return {
            "tracked_devices_online": tracked_online,
            "tracked_devices_offline": tracked_offline,
            "always_home_devices_online": always_home_online,
            "always_home_devices_offline": always_home_offline,
            "tracked_online_count": len(tracked_online),
            "tracked_offline_count": len(tracked_offline),
            "presence_detected": len(tracked_online) > 0,
        }