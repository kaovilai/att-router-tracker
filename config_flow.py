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
    AUTH_METHOD_ACCESS_CODE,
    AUTH_METHOD_SESSION_ID,
    CONF_ACCESS_CODE,
    CONF_ALWAYS_HOME_DEVICES,
    CONF_AUTH_METHOD,
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
    
    # Create client based on auth method
    if data.get(CONF_AUTH_METHOD) == AUTH_METHOD_ACCESS_CODE:
        client = ATTRouterClient(
            session, 
            data[CONF_HOST], 
            access_code=data.get(CONF_ACCESS_CODE)
        )
    else:
        client = ATTRouterClient(
            session, 
            data[CONF_HOST], 
            session_id=data.get(CONF_SESSION_ID)
        )
    
    # Test the connection
    devices = await client.get_devices()
    if devices is None:
        raise ValueError("Cannot connect to router")
    
    return {"title": f"AT&T Router ({data[CONF_HOST]})"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AT&T Router Tracker."""

    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self._auth_method = None
        self._host = DEFAULT_HOST
    
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - choose auth method."""
        if user_input is not None:
            self._auth_method = user_input[CONF_AUTH_METHOD]
            self._host = user_input[CONF_HOST]
            
            if self._auth_method == AUTH_METHOD_ACCESS_CODE:
                return await self.async_step_access_code()
            else:
                return await self.async_step_session_id()
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                    vol.Required(CONF_AUTH_METHOD, default=AUTH_METHOD_ACCESS_CODE): vol.In({
                        AUTH_METHOD_ACCESS_CODE: "Device Access Code (Recommended)",
                        AUTH_METHOD_SESSION_ID: "Session ID (Manual)",
                    }),
                }
            ),
        )
    
    async def async_step_access_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Device Access Code authentication."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            data = {
                CONF_HOST: self._host,
                CONF_AUTH_METHOD: AUTH_METHOD_ACCESS_CODE,
                CONF_ACCESS_CODE: user_input[CONF_ACCESS_CODE],
            }
            
            try:
                info = await validate_input(self.hass, data)
            except Exception as e:
                _LOGGER.error("Authentication failed: %s", e)
                errors["base"] = "invalid_auth"
            else:
                # Initialize with empty options
                data[CONF_ALWAYS_HOME_DEVICES] = []
                data[CONF_PRESENCE_DETECTION] = True
                return self.async_create_entry(title=info["title"], data=data)
        
        return self.async_show_form(
            step_id="access_code",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_CODE): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "host": self._host,
            },
        )
    
    async def async_step_session_id(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Session ID authentication."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            data = {
                CONF_HOST: self._host,
                CONF_AUTH_METHOD: AUTH_METHOD_SESSION_ID,
                CONF_SESSION_ID: user_input[CONF_SESSION_ID],
            }
            
            try:
                info = await validate_input(self.hass, data)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                # Initialize with empty options
                data[CONF_ALWAYS_HOME_DEVICES] = []
                data[CONF_PRESENCE_DETECTION] = True
                return self.async_create_entry(title=info["title"], data=data)

        return self.async_show_form(
            step_id="session_id",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SESSION_ID): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "host": self._host,
            },
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