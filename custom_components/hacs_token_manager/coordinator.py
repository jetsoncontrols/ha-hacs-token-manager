"""Coordinator that keeps HACS's token capable and self-heals drift."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_TEST_REPO,
    CONF_TOKEN,
    DOMAIN,
    HACS_DOMAIN,
    ISSUE_HACS_MISSING,
    ISSUE_PAT_INVALID,
    TOKEN_INVALID,
    TOKEN_UNKNOWN,
    UPDATE_INTERVAL,
)
from .github import async_check_token

_LOGGER = logging.getLogger(__name__)


class TokenManagerCoordinator(DataUpdateCoordinator[dict]):
    """Detect token drift/expiry and keep HACS authenticated for private repos.

    The heavy lifting is deliberately trivial:
      1. Is our managed token still valid at GitHub?  (else -> fixable repair)
      2. Is HACS installed?                            (else -> info repair)
      3. Does HACS's stored token still equal ours?    (else -> re-inject + reload)

    HACS reads its token only once, at config-entry setup, so healing means
    rewriting HACS's entry data and reloading the entry -- both public HA APIs,
    the same pair HACS itself uses in its re-auth path. We never touch HACS
    internals.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self.heal_count = 0

    def _hacs_entry(self) -> ConfigEntry | None:
        entries = self.hass.config_entries.async_entries(HACS_DOMAIN)
        return entries[0] if entries else None

    async def _async_update_data(self) -> dict:
        pat: str = self.entry.data[CONF_TOKEN]
        test_repo: str | None = self.entry.data.get(CONF_TEST_REPO)

        # 1. Is our managed token still good?
        result = await async_check_token(self.hass, pat, test_repo)
        if result == TOKEN_UNKNOWN:
            # Transient: keep the last known state, do not flip any repair.
            raise UpdateFailed("Could not reach GitHub to validate the token")
        if result == TOKEN_INVALID:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_PAT_INVALID,
                is_fixable=True,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_PAT_INVALID,
                data={"entry_id": self.entry.entry_id},
            )
            return {"healthy": False, "reason": "pat_invalid", "heal_count": self.heal_count}
        ir.async_delete_issue(self.hass, DOMAIN, ISSUE_PAT_INVALID)

        # 2. Is HACS present?
        hacs_entry = self._hacs_entry()
        if hacs_entry is None:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_HACS_MISSING,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_HACS_MISSING,
                learn_more_url="https://www.hacs.xyz",
            )
            return {"healthy": False, "reason": "hacs_missing", "heal_count": self.heal_count}
        ir.async_delete_issue(self.hass, DOMAIN, ISSUE_HACS_MISSING)

        # 3. Has HACS's token drifted away from ours? (re-auth clobber, first run)
        if hacs_entry.data.get(CONF_TOKEN) != pat:
            _LOGGER.info(
                "HACS token differs from the managed token; re-injecting the "
                "private-repo-capable token and reloading HACS"
            )
            self.hass.config_entries.async_update_entry(
                hacs_entry, data={**hacs_entry.data, CONF_TOKEN: pat}
            )
            await self.hass.config_entries.async_reload(hacs_entry.entry_id)
            self.heal_count += 1
            return {"healthy": True, "reason": "healed", "heal_count": self.heal_count}

        return {"healthy": True, "reason": "ok", "heal_count": self.heal_count}
