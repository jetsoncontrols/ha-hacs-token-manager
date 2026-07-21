"""Config flow for HACS Private Token Manager.

Two ways to provide a private-repo-capable GitHub token:
  * device  - browser login (GitHub device flow), like HACS. Preferred.
  * manual  - paste a token (classic repo PAT or fine-grained PAT). For
              headless/automated setup where a browser flow is impractical.
"""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CLIENT_ID,
    CONF_TEST_REPO,
    CONF_TOKEN,
    DOMAIN,
    GITHUB_DEVICE_URL,
    TOKEN_INVALID,
    TOKEN_UNKNOWN,
)
from .github import async_check_token
from .github_device import (
    DeviceFlowError,
    async_start_device_flow,
    async_wait_for_token,
)

_MANUAL_SCHEMA = vol.Schema(
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

    def __init__(self) -> None:
        self._device: dict | None = None
        self._task: asyncio.Task[str] | None = None
        self._token: str | None = None
        self._error: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick browser login or a manual token."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_show_menu(step_id="user", menu_options=["device", "manual"])

    # ------------------------------------------------------------------ device
    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run the GitHub device flow with a live progress screen."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if not CLIENT_ID:
            return self.async_abort(reason="no_client_id")

        # Token already obtained on a previous pass -> finish.
        if self._token is not None:
            return self._create_entry(self._token)

        if self._device is None:
            try:
                self._device = await async_start_device_flow(self.hass, CLIENT_ID)
            except DeviceFlowError as err:
                return self.async_abort(reason=err.reason)

        if self._task is None:
            self._task = self.hass.async_create_task(
                async_wait_for_token(self.hass, CLIENT_ID, self._device)
            )

        if self._task.done():
            try:
                self._token = self._task.result()
            except DeviceFlowError as err:
                self._error = err.reason
                self._device = None
                self._task = None
                return self.async_show_progress_done(next_step_id="device_failed")
            return self.async_show_progress_done(next_step_id="device")

        return self.async_show_progress(
            step_id="device",
            progress_action="wait_for_device",
            description_placeholders={
                "url": self._device.get("verification_uri", GITHUB_DEVICE_URL),
                "code": self._device.get("user_code", ""),
            },
            progress_task=self._task,
        )

    async def async_step_device_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Abort with the device-flow failure reason."""
        return self.async_abort(reason=self._error or "device_flow_failed")

    # ------------------------------------------------------------------ manual
    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect and validate a token pasted by hand."""
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
            step_id="manual", data_schema=_MANUAL_SCHEMA, errors=errors
        )

    # ------------------------------------------------------------- reconfigure
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Rotate the stored token (manual paste)."""
        entry = self._get_reconfigure_entry()

        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = await self._validate(user_input)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reconfigure", data_schema=_MANUAL_SCHEMA, errors=errors
        )

    # ------------------------------------------------------------------ helpers
    async def _validate(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        errors: dict[str, str] = {}
        token = user_input[CONF_TOKEN].strip()
        test_repo = (user_input.get(CONF_TEST_REPO) or "").strip() or None

        result = await async_check_token(self.hass, token, test_repo)
        if result == TOKEN_UNKNOWN:
            errors["base"] = "cannot_connect"
        elif result == TOKEN_INVALID:
            errors["base"] = "invalid_token"

        return {CONF_TOKEN: token, CONF_TEST_REPO: test_repo}, errors

    def _create_entry(self, token: str) -> ConfigFlowResult:
        return self.async_create_entry(
            title="HACS Private Token Manager",
            data={CONF_TOKEN: token, CONF_TEST_REPO: None},
        )
