"""Client for AT&T Router."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from .auth import ATTRouterAuth

_LOGGER = logging.getLogger(__name__)


class ATTRouterClient:
    """Client to interact with AT&T Router."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        session_id: str | None = None,
        access_code: str | None = None,
    ) -> None:
        """Initialize the client."""
        self.session = session
        self.host = host
        self.session_id = session_id
        self.access_code = access_code
        self.url = f"http://{host}/cgi-bin/devices.ha"
        self.auth = ATTRouterAuth(session, host) if access_code else None
        self._auth_failures = 0
        
    async def _ensure_authenticated(self) -> bool:
        """Ensure we have a valid session, authenticate if needed."""
        # If we have access code but no session, authenticate
        if self.access_code and not self.session_id:
            _LOGGER.debug("No session ID, authenticating with access code")
            self.session_id = await self.auth.authenticate_with_access_code(self.access_code)
            if self.session_id:
                self._auth_failures = 0
                return True
            return False
        
        # If we have auth capability, validate current session
        if self.auth and self.session_id:
            is_valid = await self.auth.validate_session(self.session_id)
            if not is_valid:
                _LOGGER.info("Session expired, re-authenticating")
                self.session_id = await self.auth.authenticate_with_access_code(self.access_code)
                if self.session_id:
                    self._auth_failures = 0
                    return True
                return False
        
        # If we only have session ID (legacy mode), assume it's valid
        return self.session_id is not None
    
    async def get_devices(self) -> list[dict[str, Any]] | None:
        """Get list of devices from router."""
        # Ensure we're authenticated
        if not await self._ensure_authenticated():
            _LOGGER.error("Failed to authenticate with router")
            return None
        
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Cookie": f"SessionID={self.session_id}",
            "DNT": "1",
            "Pragma": "no-cache",
            "Referer": f"http://{self.host}/cgi-bin/home.ha",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        
        try:
            async with self.session.get(
                self.url, headers=headers, ssl=False, timeout=30, allow_redirects=False
            ) as response:
                # Check if we got redirected to login
                if response.status in [302, 303]:
                    location = response.headers.get("Location", "")
                    if "login" in location.lower():
                        _LOGGER.warning("Session expired during request")
                        # If we have auth capability, try to re-authenticate once
                        if self.auth and self._auth_failures < 2:
                            self._auth_failures += 1
                            self.session_id = None
                            return await self.get_devices()  # Retry once
                        return None
                
                if response.status != 200:
                    _LOGGER.error("Failed to get devices: HTTP %s", response.status)
                    return None
                    
                html = await response.text()
                
                # Check if response is actually a login page
                if "login" in html.lower() and "password" in html.lower():
                    _LOGGER.warning("Got login page instead of device list")
                    if self.auth and self._auth_failures < 2:
                        self._auth_failures += 1
                        self.session_id = None
                        return await self.get_devices()  # Retry once
                    return None
                
                self._auth_failures = 0  # Reset on success
                return self._parse_devices(html)
                
        except aiohttp.ClientError as err:
            _LOGGER.error("Error connecting to router: %s", err)
            return None
        except Exception as err:
            _LOGGER.error("Unexpected error: %s", err)
            return None
    
    def _parse_devices(self, html: str) -> list[dict[str, Any]]:
        """Parse devices from HTML."""
        devices = []
        soup = BeautifulSoup(html, "lxml")
        
        # Find all table rows
        rows = soup.find_all("tr")
        
        current_device = {}
        
        for row in rows:
            th = row.find("th", scope="row")
            td = row.find("td", class_="col2")
            
            if not th or not td:
                # Check for separator (end of device)
                if row.find("hr", class_="reshr"):
                    if current_device and "mac" in current_device:
                        devices.append(current_device)
                        current_device = {}
                continue
            
            label = th.get_text(strip=True)
            value = td.get_text(strip=True)
            
            if label == "MAC Address":
                current_device["mac"] = value.lower().replace(":", "")
                current_device["mac_formatted"] = value.lower()
            elif label == "IPv4 Address / Name":
                parts = value.split("/", 1)
                current_device["ip"] = parts[0].strip()
                if len(parts) > 1:
                    current_device["name"] = parts[1].strip()
            elif label == "Name":
                current_device["name"] = value
            elif label == "Status":
                current_device["status"] = value
                current_device["is_online"] = value.lower() == "on"
            elif label == "Last Activity":
                current_device["last_activity"] = value
            elif label == "Allocation":
                current_device["allocation"] = value
            elif label == "Connection Type":
                # Extract connection type and signal strength
                conn_text = td.get_text(" ", strip=True)
                current_device["connection_type"] = self._parse_connection_type(conn_text, td)
            elif label == "Connection Speed":
                if value:
                    current_device["connection_speed"] = value
        
        # Don't forget the last device
        if current_device and "mac" in current_device:
            devices.append(current_device)
        
        return devices
    
    def _parse_connection_type(self, text: str, td_element) -> dict[str, Any]:
        """Parse connection type details."""
        result = {"raw": text}
        
        # Check if it's ethernet
        if "Ethernet" in text:
            result["type"] = "ethernet"
            result["interface"] = text.strip()
        # Check if it's Wi-Fi
        elif "Wi-Fi" in text:
            result["type"] = "wifi"
            
            # Extract signal strength from image
            img = td_element.find("img")
            if img and img.get("alt"):
                alt_text = img["alt"]
                bars_match = re.search(r"(\d+) bars?", alt_text)
                if bars_match:
                    result["signal_bars"] = int(bars_match.group(1))
            
            # Extract band and network info
            lines = text.split()
            for i, line in enumerate(lines):
                if "GHz" in line:
                    # Get the frequency band
                    if i > 0:
                        result["band"] = lines[i-1] + " " + line
                elif line == "Name:":
                    # Get network name
                    if i + 1 < len(lines):
                        result["network_name"] = lines[i + 1]
        
        return result