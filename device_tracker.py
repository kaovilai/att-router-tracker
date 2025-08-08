"""Device tracker platform for AT&T Router."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.device_tracker import (
    DOMAIN as DEVICE_TRACKER_DOMAIN,
    SourceType,
)
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    ATTR_ALLOCATION,
    ATTR_CONNECTION_SPEED,
    ATTR_CONNECTION_TYPE,
    ATTR_IP,
    ATTR_LAST_ACTIVITY,
    ATTR_MAC,
    ATTR_NAME,
    ATTR_SIGNAL_STRENGTH,
    ATTR_STATUS,
    CONF_ALWAYS_HOME_DEVICES,
    CONF_SESSION_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .router_client import ATTRouterClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device tracker for AT&T Router."""
    session = aiohttp_client.async_get_clientsession(hass)
    client = ATTRouterClient(
        session, entry.data[CONF_HOST], entry.data[CONF_SESSION_ID]
    )
    
    async def async_update_data():
        """Fetch data from router."""
        devices = await client.get_devices()
        if devices is None:
            _LOGGER.error("Failed to fetch devices from router")
            return {}
        
        # Convert list to dict keyed by MAC address
        return {device["mac"]: device for device in devices if "mac" in device}
    
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"att_router_{entry.data[CONF_HOST]}",
        update_method=async_update_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )
    
    # Initial refresh
    await coordinator.async_config_entry_first_refresh()
    
    # Create entities for all discovered devices (excluding always-home devices)
    always_home = entry.data.get(CONF_ALWAYS_HOME_DEVICES, [])
    entities = []
    for mac, device in coordinator.data.items():
        # Only create device tracker for non-always-home devices
        if mac not in always_home:
            entities.append(ATTRouterDevice(coordinator, mac, device, entry))
    
    async_add_entities(entities, True)
    
    # Store coordinator for sensor platform
    hass.data[DOMAIN][entry.entry_id] = coordinator


class ATTRouterDevice(CoordinatorEntity, ScannerEntity):
    """Representation of a device connected to AT&T Router."""
    
    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        mac: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the device."""
        super().__init__(coordinator)
        self._mac = mac
        self._device = device
        self._entry = entry
        self._attr_unique_id = f"att_router_{mac}"
        
    @property
    def name(self) -> str:
        """Return the name of the device."""
        if self._mac not in self.coordinator.data:
            return f"Unknown Device ({self._mac})"
        
        device = self.coordinator.data[self._mac]
        return device.get("name", f"Device {self._mac}")
    
    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected."""
        if self._mac not in self.coordinator.data:
            return False
        
        device = self.coordinator.data[self._mac]
        return device.get("is_online", False)
    
    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.ROUTER
    
    @property
    def mac_address(self) -> str:
        """Return the MAC address."""
        return self._mac
    
    @property
    def ip_address(self) -> str | None:
        """Return the IP address."""
        if self._mac not in self.coordinator.data:
            return None
        
        device = self.coordinator.data[self._mac]
        return device.get("ip")
    
    @property
    def icon(self) -> str:
        """Return the icon."""
        if self._mac not in self.coordinator.data:
            return "mdi:help-network"
        
        device = self.coordinator.data[self._mac]
        conn_type = device.get("connection_type", {})
        
        if isinstance(conn_type, dict):
            if conn_type.get("type") == "ethernet":
                return "mdi:ethernet"
            elif conn_type.get("type") == "wifi":
                signal_bars = conn_type.get("signal_bars", 0)
                if signal_bars >= 4:
                    return "mdi:wifi-strength-4"
                elif signal_bars == 3:
                    return "mdi:wifi-strength-3"
                elif signal_bars == 2:
                    return "mdi:wifi-strength-2"
                elif signal_bars == 1:
                    return "mdi:wifi-strength-1"
                else:
                    return "mdi:wifi"
        
        return "mdi:devices"
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self._mac not in self.coordinator.data:
            return {}
        
        device = self.coordinator.data[self._mac]
        attributes = {
            ATTR_MAC: device.get("mac_formatted", self._mac),
        }
        
        if "ip" in device:
            attributes[ATTR_IP] = device["ip"]
        if "status" in device:
            attributes[ATTR_STATUS] = device["status"]
        if "last_activity" in device:
            attributes[ATTR_LAST_ACTIVITY] = device["last_activity"]
        if "allocation" in device:
            attributes[ATTR_ALLOCATION] = device["allocation"]
        if "connection_speed" in device:
            attributes[ATTR_CONNECTION_SPEED] = device["connection_speed"]
        
        # Connection type details
        conn_type = device.get("connection_type", {})
        if isinstance(conn_type, dict):
            if conn_type.get("type"):
                attributes[ATTR_CONNECTION_TYPE] = conn_type.get("type")
            if conn_type.get("signal_bars"):
                attributes[ATTR_SIGNAL_STRENGTH] = f"{conn_type['signal_bars']} bars"
            if conn_type.get("band"):
                attributes["wifi_band"] = conn_type["band"]
            if conn_type.get("network_name"):
                attributes["network_name"] = conn_type["network_name"]
            if conn_type.get("interface"):
                attributes["interface"] = conn_type["interface"]
        
        return attributes