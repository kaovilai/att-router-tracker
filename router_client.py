"""Client for AT&T Router."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)


class ATTRouterClient:
    """Client to interact with AT&T Router."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        session_id: str,
    ) -> None:
        """Initialize the client."""
        self.session = session
        self.host = host
        self.session_id = session_id
        self.url = f"http://{host}/cgi-bin/devices.ha"
        
    async def get_devices(self) -> list[dict[str, Any]] | None:
        """Get list of devices from router."""
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
                self.url, headers=headers, ssl=False, timeout=30
            ) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to get devices: HTTP %s", response.status)
                    return None
                    
                html = await response.text()
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