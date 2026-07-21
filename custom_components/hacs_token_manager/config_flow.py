"""Config flow for HACS Private Token Manager."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_TEST_REPO,
    CONF_TOKEN,
    DOMAIN,
    TOKEN_INVALID,
    TOKEN_UNKNOWN,
)
from .github import async_check_token

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_TEST_REPO): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
    }
)


class TokenManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the token manager."""

    VERSION = 1

    async def _validate(self, user_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        """Validate input; return (cleaned_data, errors)."""
        errors: dict[str, str] = {}
        token = user_input[CONF_TOKEN].strip()
        test_repo = (user_input.get(CONF_TEST_REPO) or "").strip() or None

        result = await async_check_token(self.hass, token, test_repo)
        if result == TOKEN_UNKNOWN:
            errors["base"] = "cannot_connect"
        elif result == TOKEN_INVALID:
            errors["base"] = "invalid_token"

        return {CONF_TOKEN: token, CONF_TEST_REPO: test_repo}, errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initial setup: collect and validate a GitHub token."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = await self._validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title="HACS Private Token Manager", data=data
                )

        return self.async_show_form(
            step_id="user", data_schema=_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Rotate the stored GitHub token."""
        entry = self._get_reconfigure_entry()

        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = await self._validate(user_input)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reconfigure", data_schema=_SCHEMA, errors=errors
        )
