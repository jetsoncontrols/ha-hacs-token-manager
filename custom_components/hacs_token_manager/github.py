"""Minimal GitHub token checks using Home Assistant's shared aiohttp session.

Kept dependency-free on purpose: we only need a couple of authenticated GET
requests, so there is no reason to pull in a GitHub client library.
"""

from __future__ import annotations

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    GITHUB_API,
    GITHUB_HEADERS,
    TOKEN_INVALID,
    TOKEN_UNKNOWN,
    TOKEN_VALID,
)


def _auth_headers(token: str) -> dict[str, str]:
    return {**GITHUB_HEADERS, "Authorization": f"Bearer {token}"}


async def async_check_token(
    hass: HomeAssistant, token: str, test_repo: str | None = None
) -> str:
    """Classify a GitHub token.

    Returns one of:
      TOKEN_VALID   - token authenticates (and can read ``test_repo`` if given)
      TOKEN_INVALID - GitHub definitively rejected the token or denied the repo
      TOKEN_UNKNOWN - transient/ambiguous (network error, rate limit, 5xx)

    UNKNOWN is treated as "don't act on it" by callers, so a GitHub outage or
    a rate-limited request never raises a false "your token expired" repair.
    """
    session = async_get_clientsession(hass)
    headers = _auth_headers(token)

    try:
        async with session.get(f"{GITHUB_API}/rate_limit", headers=headers) as resp:
            if resp.status == 401:
                return TOKEN_INVALID
            if resp.status != 200:
                # 403 (rate limit / secondary limit), 5xx, etc. -> ambiguous
                return TOKEN_UNKNOWN

        if test_repo:
            async with session.get(
                f"{GITHUB_API}/repos/{test_repo}", headers=headers
            ) as resp:
                if resp.status == 200:
                    return TOKEN_VALID
                if resp.status in (401, 404):
                    # 404 with an authenticating token == cannot see this repo,
                    # which is exactly the "not capable for private" signal.
                    return TOKEN_INVALID
                return TOKEN_UNKNOWN

        return TOKEN_VALID
    except aiohttp.ClientError:
        return TOKEN_UNKNOWN
