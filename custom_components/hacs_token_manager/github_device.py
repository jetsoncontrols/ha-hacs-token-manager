"""GitHub OAuth App device-flow helpers (dependency-free).

Implements the same browser-login flow HACS uses, but against our own OAuth
App requesting the ``repo`` scope, so the resulting token can read every
private repository the authorizing user can access.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    GITHUB_ACCESS_TOKEN_URL,
    GITHUB_DEVICE_CODE_URL,
    GITHUB_DEVICE_GRANT,
    GITHUB_SCOPE,
)

_LOGGER = logging.getLogger(__name__)


class DeviceFlowError(Exception):
    """Terminal device-flow failure. ``reason`` maps to a config-flow abort key."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def async_start_device_flow(hass: HomeAssistant, client_id: str) -> dict:
    """Begin the device flow.

    Returns the GitHub payload: device_code, user_code, verification_uri,
    expires_in, interval.
    """
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            GITHUB_DEVICE_CODE_URL,
            headers={"Accept": "application/json"},
            data={"client_id": client_id, "scope": GITHUB_SCOPE},
        ) as resp:
            if resp.status != 200:
                raise DeviceFlowError("cannot_connect")
            payload = await resp.json()
    except aiohttp.ClientError as err:
        raise DeviceFlowError("cannot_connect") from err

    if "device_code" not in payload:
        # Most commonly: Device Flow is not enabled on the OAuth App.
        raise DeviceFlowError("device_flow_disabled")
    return payload


async def async_wait_for_token(
    hass: HomeAssistant, client_id: str, device: dict
) -> str:
    """Poll GitHub until the user authorizes; return the access token.

    Raises DeviceFlowError on denial, expiry, or a terminal error.
    """
    session = async_get_clientsession(hass)
    # GitHub asks us to wait at least ``interval`` seconds between polls; add a
    # small margin to avoid slow_down responses.
    interval = int(device.get("interval", 5)) + 1
    remaining = int(device.get("expires_in", 900))

    polls = 0
    while remaining > 0:
        await asyncio.sleep(interval)
        remaining -= interval
        polls += 1
        try:
            async with session.post(
                GITHUB_ACCESS_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "device_code": device["device_code"],
                    "grant_type": GITHUB_DEVICE_GRANT,
                },
            ) as resp:
                payload = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            _LOGGER.debug("device-flow poll %s: client error %s", polls, err)
            continue  # transient network error; keep polling

        if token := payload.get("access_token"):
            _LOGGER.debug("device-flow poll %s: access token received", polls)
            return token

        error = payload.get("error")
        _LOGGER.debug("device-flow poll %s: error=%s", polls, error)
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval = int(payload.get("interval", interval)) + 1
            continue
        if error in ("expired_token", "access_denied"):
            raise DeviceFlowError(error)
        # incorrect_client_credentials, unsupported_grant_type, etc.
        raise DeviceFlowError("device_flow_failed")

    raise DeviceFlowError("expired_token")
