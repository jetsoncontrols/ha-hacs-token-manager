"""Repair flows for HACS Private Token Manager."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_TEST_REPO,
    CONF_TOKEN,
    TOKEN_INVALID,
    TOKEN_UNKNOWN,
)
from .github import async_check_token


class PatFixFlow(RepairsFlow):
    """Collect a fresh GitHub token when the stored one has gone invalid."""

    def __init__(self, entry_id: str | None) -> None:
        self._entry_id = entry_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = (
            self.hass.config_entries.async_get_entry(self._entry_id)
            if self._entry_id
            else None
        )
        if entry is None:
            return self.async_abort(reason="entry_missing")

        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            test_repo = entry.data.get(CONF_TEST_REPO)
            result = await async_check_token(self.hass, token, test_repo)
            if result == TOKEN_UNKNOWN:
                errors["base"] = "cannot_connect"
            elif result == TOKEN_INVALID:
                errors["base"] = "invalid_token"
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_TOKEN: token}
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the repair flow for a raised issue."""
    entry_id = (data or {}).get("entry_id")
    return PatFixFlow(entry_id)
