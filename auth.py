"""Authentication module for AT&T Router."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)


class ATTRouterAuth:
    """Handle authentication with AT&T Router."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
    ) -> None:
        """Initialize the auth client."""
        self.session = session
        self.host = host
        self.base_url = f"http://{host}"
        self.session_id = None
        
    async def authenticate_with_access_code(self, access_code: str) -> str | None:
        """Authenticate using Device Access Code and return session ID."""
        try:
            # Step 1: Get the login page to extract any necessary tokens/nonces
            login_url = f"{self.base_url}/cgi-bin/login.ha"
            
            async with self.session.get(
                self.base_url,
                ssl=False,
                timeout=30,
                allow_redirects=True
            ) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to get login page: HTTP %s", response.status)
                    return None
                
                html = await response.text()
                
                # Check if we're already logged in (redirected to home)
                if "home.ha" in str(response.url) or "Device Status" in html:
                    # Extract session ID from cookies
                    cookies = response.cookies
                    for cookie in cookies:
                        if cookie.key == "SessionID":
                            self.session_id = cookie.value
                            _LOGGER.debug("Already logged in with session: %s", self.session_id[:8])
                            return self.session_id
                
                # Parse the login form to get any hidden fields
                soup = BeautifulSoup(html, "lxml")
                form = soup.find("form")
                
                if not form:
                    _LOGGER.error("Login form not found on page")
                    return None
                
                # Extract form action and hidden fields
                action = form.get("action", "/cgi-bin/login.ha")
                if not action.startswith("http"):
                    action = f"{self.base_url}{action}" if action.startswith("/") else f"{self.base_url}/{action}"
                
                form_data = {}
                
                # Get all hidden inputs
                for hidden in form.find_all("input", type="hidden"):
                    name = hidden.get("name")
                    value = hidden.get("value", "")
                    if name:
                        form_data[name] = value
                
                # Add the access code field
                # Look for the password/PIN input field name
                password_input = form.find("input", type="password")
                if password_input:
                    password_field_name = password_input.get("name", "password")
                else:
                    # Common field names for AT&T routers
                    password_field_name = "password"
                    for possible_name in ["accessCode", "access_code", "pin", "PIN", "deviceAccessCode"]:
                        if form.find("input", {"name": possible_name}):
                            password_field_name = possible_name
                            break
                
                form_data[password_field_name] = access_code
                
                # Some routers may require a username field
                username_input = form.find("input", type="text")
                if username_input and username_input.get("name"):
                    # AT&T routers typically use "admin" or leave it empty
                    form_data[username_input.get("name")] = "admin"
                
                _LOGGER.debug("Submitting login form to %s", action)
                
                # Step 2: Submit the login form
                async with self.session.post(
                    action,
                    data=form_data,
                    ssl=False,
                    timeout=30,
                    allow_redirects=False,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Referer": self.base_url,
                        "Origin": self.base_url,
                    }
                ) as login_response:
                    
                    # Check for redirect (successful login)
                    if login_response.status in [302, 303]:
                        location = login_response.headers.get("Location", "")
                        _LOGGER.debug("Login redirected to: %s", location)
                    
                    # Extract session ID from cookies
                    for cookie in login_response.cookies:
                        if cookie.key == "SessionID":
                            self.session_id = cookie.value
                            _LOGGER.info("Successfully authenticated, session ID: %s...", self.session_id[:8])
                            return self.session_id
                    
                    # If no cookie in response, check if we need to follow redirect
                    if login_response.status in [302, 303]:
                        redirect_url = login_response.headers.get("Location", "")
                        if not redirect_url.startswith("http"):
                            redirect_url = f"{self.base_url}{redirect_url}" if redirect_url.startswith("/") else f"{self.base_url}/{redirect_url}"
                        
                        async with self.session.get(
                            redirect_url,
                            ssl=False,
                            timeout=30
                        ) as redirect_response:
                            for cookie in redirect_response.cookies:
                                if cookie.key == "SessionID":
                                    self.session_id = cookie.value
                                    _LOGGER.info("Got session ID after redirect: %s...", self.session_id[:8])
                                    return self.session_id
                    
                    # Check response body for errors
                    if login_response.status == 200:
                        response_text = await login_response.text()
                        if "incorrect" in response_text.lower() or "invalid" in response_text.lower():
                            _LOGGER.error("Invalid Device Access Code")
                        else:
                            _LOGGER.error("Login failed - no session cookie received")
                    
        except asyncio.TimeoutError:
            _LOGGER.error("Login timeout - router not responding")
        except aiohttp.ClientError as err:
            _LOGGER.error("Login connection error: %s", err)
        except Exception as err:
            _LOGGER.error("Unexpected login error: %s", err)
        
        return None
    
    async def validate_session(self, session_id: str) -> bool:
        """Validate if a session ID is still valid."""
        try:
            headers = {
                "Cookie": f"SessionID={session_id}",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            
            # Try to access a protected page
            async with self.session.get(
                f"{self.base_url}/cgi-bin/devices.ha",
                headers=headers,
                ssl=False,
                timeout=10,
                allow_redirects=False
            ) as response:
                # If we get redirected to login, session is invalid
                if response.status in [302, 303]:
                    location = response.headers.get("Location", "")
                    if "login" in location.lower():
                        return False
                
                # If we get the page content, check it's not a login page
                if response.status == 200:
                    text = await response.text()
                    if "Device List" in text or "MAC Address" in text:
                        return True
                    if "login" in text.lower() or "password" in text.lower():
                        return False
                
                return response.status == 200
                
        except Exception as err:
            _LOGGER.debug("Session validation error: %s", err)
            return False
    
    def get_session_id(self) -> str | None:
        """Get the current session ID."""
        return self.session_id