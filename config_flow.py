"""Config flow for AT&T Router Tracker."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ALWAYS_HOME_DEVICES,
    CONF_PRESENCE_DETECTION,
    CONF_SESSION_ID,
    DEFAULT_HOST,
    DOMAIN,
)
from .router_client import ATTRouterClient

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = aiohttp_client.async_get_clientsession(hass)
    client = ATTRouterClient(session, data[CONF_HOST], data[CONF_SESSION_ID])
    
    # Test the connection
    devices = await client.get_devices()
    if devices is None:
        raise ValueError("Cannot connect to router")
    
    return {"title": f"AT&T Router ({data[CONF_HOST]})"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AT&T Router Tracker."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                # Initialize with empty options
                user_input[CONF_ALWAYS_HOME_DEVICES] = []
                user_input[CONF_PRESENCE_DETECTION] = True
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                    vol.Required(CONF_SESSION_ID): str,
                }
            ),
            errors=errors,
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for AT&T Router Tracker."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update config entry with new options
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_ALWAYS_HOME_DEVICES: user_input.get(CONF_ALWAYS_HOME_DEVICES, []),
                    CONF_PRESENCE_DETECTION: user_input.get(CONF_PRESENCE_DETECTION, True),
                },
            )
            return self.async_create_entry(title="", data={})

        # Get current devices from coordinator
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        device_options = {}
        
        if coordinator and coordinator.data:
            # Create a list of device options (MAC: Name)
            for mac, device in coordinator.data.items():
                name = device.get("name", f"Unknown ({mac})")
                ip = device.get("ip", "No IP")
                device_options[mac] = f"{name} ({ip})"
        
        current_always_home = self.config_entry.data.get(CONF_ALWAYS_HOME_DEVICES, [])
        presence_detection = self.config_entry.data.get(CONF_PRESENCE_DETECTION, True)
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ALWAYS_HOME_DEVICES,
                        default=current_always_home,
                    ): cv.multi_select(device_options),
                    vol.Optional(
                        CONF_PRESENCE_DETECTION,
                        default=presence_detection,
                    ): bool,
                }
            ),
        )