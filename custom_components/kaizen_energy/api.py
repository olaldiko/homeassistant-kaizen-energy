# Copyright (C) 2021-2023 Gorka Olalde Mendia
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

"""API client for Tridens Monetization (Kaizen Energy)."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

import aiohttp
from attr import dataclass
import jwt

from homeassistant.exceptions import HomeAssistantError

from .const import TRIDENS_SITE

_LOGGER = logging.getLogger(__name__)


# Define custom exceptions for our Config Flow
class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


@dataclass
class ConsumptionRecord:
    """Data structure for consumption records."""

    time_of_read: datetime
    consumption: float
    cost: float


class TridensApiClient:
    """Class to manage communication with the Tridens API."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API client."""
        self._username = username
        self._password = password
        self._session = session
        self._access_token: str | None = None
        self._customer_code: str | None = None
        self._customer_id: str | None = None
        self._group_id: str | None = None
        self._balance_group_id: str | None = None
        self._site_code = TRIDENS_SITE
        self._base_url = "https://app.tridenstechnology.com/monetization"
        self._service_type = "HEAT_METER_READ_SERVICE"
        # ------------------------------------------

    async def async_get_token(self) -> str | None:
        """Get a new access token from the API."""
        auth_url = f"{self._base_url}/authenticate"
        auth_payload = {
            "username": self._username,
            "password": self._password,
            "site_code": self._site_code,
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        _LOGGER.debug("Attempting to authenticate user %s", self._username)
        try:
            async with self._session.post(
                auth_url, headers=headers, json=auth_payload
            ) as response:
                if response.status in (401, 403):
                    _LOGGER.error("Invalid credentials for user %s", self._username)
                    raise InvalidAuth

                response.raise_for_status()  # Raise on other bad statuses (404, 500)

                token_data = await response.json()

                if "access_token" in token_data:
                    self._access_token = token_data["access_token"]
                    self._set_customer_code_from_token(self._access_token)
                    return self._access_token
                if "token" in token_data:
                    self._access_token = token_data["token"]
                    self._set_customer_code_from_token(self._access_token)
                    return self._access_token

                _LOGGER.error("No 'access_token' or 'token' in auth response")
                raise CannotConnect

        except aiohttp.ClientError as err:
            _LOGGER.error("Cannot connect to Tridens auth endpoint: %s", err)
            raise CannotConnect from err

    async def async_test_authentication(self) -> bool:
        """Test authentication by fetching a token."""
        # This wrapper is used by the config flow
        await self.async_get_token()
        return True

    def _set_customer_code_from_token(self, access_token):
        token_json = jwt.decode(access_token, options={"verify_signature": False})
        self._customer_code = token_json.get("customer_code")

    async def _get_customer_data(self) -> str | None:
        """Collect customer data fields."""
        if self._customer_code is None:
            await self.async_get_token()
        url = f"{self._base_url}/api/v1/customers/{self._customer_code}"
        data = await self._api_request("GET", url)
        try:
            groups = data.get("groups")
            self._group_id = groups[0]["id"]
            _LOGGER.info("Successfully obtained customer group information")
        except:
            _LOGGER.error("Unable to obtain customer group information")

    async def _get_subscription_data(self) -> str | None:
        """Collect subscription data fields."""
        if self._group_id is None:
            await self._get_customer_data()
        params = {"parent-group": self._group_id}
        url = f"{self._base_url}/api/v1/customers"
        data = await self._api_request("GET", url, params=params)
        try:
            self._balance_group_id = data["objects"][0]["subscriptions"][0][
                "balance_group"
            ]["id"]
            self._customer_id = data["objects"][0]["id"]
            _LOGGER.info("Successfully obtained subscription data")
        except ValueError:
            _LOGGER.error("Balance group and customer ID not found")

    async def _api_request(self, method: str, url: str, **kwargs) -> Any:
        """Make an authenticated API request.

        Handles token refresh on 401.
        """
        if self._access_token is None:
            await self.async_get_token()

        headers = kwargs.get("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"
        headers["Accept"] = "application/json"
        headers["Response-Type"] = "full"
        kwargs["headers"] = headers

        try:
            async with self._session.request(method, url, **kwargs) as response:
                if response.status in (401, 403):
                    _LOGGER.warning("Token expired or invalid, re-authenticating")
                    # Token is bad, get a new one and retry *once*
                    await self.async_get_token()
                    headers["Authorization"] = f"Bearer {self._access_token}"

                    async with self._session.request(
                        method, url, **kwargs
                    ) as retry_response:
                        retry_response.raise_for_status()
                        return await retry_response.json()

                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientError as err:
            _LOGGER.error("Error during API request: %s", err)
            raise CannotConnect from err

    async def fetch_consumption(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[ConsumptionRecord]:
        """Fetch consumption data from the API."""
        if self._customer_id is None or self._balance_group_id is None:
            await self._get_subscription_data()
        url = f"{self._base_url}/api/v1/customers/{self._customer_id}/usage-events"
        params = {
            "service_type": self._service_type,
            "page": 1,
            "count": 100,
            "order-dir": "desc",
        }
        if start:
            params["time-from"] = int(start.timestamp()) * 1000
        if end:
            params["time-to"] = int(end.timestamp()) * 1000
        data = await self._api_request("GET", url, params=params)
        records = []
        for item in data.get("objects", []):
            record = ConsumptionRecord(
                time_of_read=datetime.fromtimestamp(
                    int(item["fields"]["time_of_read"]) / 1000
                ),
                consumption=float(item["quantity"]),
                cost=float(item["amount_with_discount"]),
            )
            records.append(record)
        _LOGGER.info("Successfully obtained consumption data")
        return records
