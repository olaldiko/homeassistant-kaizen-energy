"""Config flow for Kaizen Energy integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .api import CannotConnect, InvalidAuth, TridensApiClient

# Get a logger for troubleshooting
_LOGGER = logging.getLogger(__name__)

# Define the data schema for the user input form
# This creates the fields for Username, Password, Site Code and Customer ID
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    'data' contains the user input from the form:
    data[CONF_USERNAME]
    data[CONF_PASSWORD]
    """
    session = aiohttp.ClientSession()
    try:
        hub = TridensApiClient(
            data["username"],
            data["password"],
            session,
        )

        if not await hub.async_test_authentication():
            raise InvalidAuth

        # If we get here, connection is OK

        _LOGGER.info("Simulating successful authentication for %s", data["username"])

        # Return info we want to store in the config entry.
        # We'll use the username as the unique title for the integration entry.
        return {"title": data["username"]}
    finally:
        await session.close()


class ConfigFlow(config_entries.ConfigFlow, domain="tridens"):
    """Handle a config flow for Kaizen Energy."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Check for duplicate entry using username as unique identifier
            await self.async_set_unique_id(user_input["username"])
            self._abort_if_unique_id_configured()

            try:
                # Test the user's credentials
                info = await validate_input(self.hass, user_input)

                # If validation is successful, create the config entry
                return self.async_create_entry(title=info["title"], data=user_input)

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # If we get here, it's either the first time the user sees the form,
        # or an error occurred and we're showing the form again with an error message.
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
