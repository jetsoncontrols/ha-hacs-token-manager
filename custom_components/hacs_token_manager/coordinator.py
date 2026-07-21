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
    ISSUE_DOWNLOAD_AUTH,
    ISSUE_HACS_MISSING,
    ISSUE_PAT_INVALID,
    ISSUE_RESTART_REQUIRED,
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
      3. Does HACS's stored token still equal ours?    (else -> inject + restart
         repair)

    Why we do NOT reload HACS: HACS registers ``add_update_listener`` and
    reloads itself on any config-entry change, and that reload is unsafe -- it
    forwards its switch/update platforms in a deferred startup stage, so a
    reload triggered from outside races that and leaves HACS in FAILED_UNLOAD.
    So when we write the token into HACS's entry we SUPPRESS that listener (the
    update just persists), leaving HACS running normally on its old token, and
    ask the user to restart via a fixable Repair. On the next start HACS loads
    fresh with our token and the repair clears itself.
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
        # Set once we inject this session; only a restart clears it.
        self._restart_pending = False
        # Set by async_setup_entry: did the HACS download-auth patch apply?
        self.download_auth_ok = True

    def _hacs_entry(self) -> ConfigEntry | None:
        entries = self.hass.config_entries.async_entries(HACS_DOMAIN)
        return entries[0] if entries else None

    def _inject_token(self, hacs_entry: ConfigEntry, pat: str) -> None:
        """Write our token into HACS's entry WITHOUT triggering HACS's reload.

        HACS reloads itself on any entry update (add_update_listener), and that
        reload is unsafe. Detach HACS's update listeners for the duration of the
        write so the new token simply persists; restore them afterwards (same
        listener objects, so HACS's unlisten callbacks stay valid). The token
        takes effect on the next HA restart.
        """
        listeners = list(hacs_entry.update_listeners)
        hacs_entry.update_listeners.clear()
        try:
            self.hass.config_entries.async_update_entry(
                hacs_entry, data={**hacs_entry.data, CONF_TOKEN: pat}
            )
        finally:
            hacs_entry.update_listeners[:] = listeners

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

        # 2b. Could we authenticate HACS's downloads? If the patch could not be
        # applied (HACS internals moved), private-repo installs will fail --
        # surface it rather than let it fail silently on the next install.
        if not self.download_auth_ok:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_DOWNLOAD_AUTH,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_DOWNLOAD_AUTH,
                learn_more_url="https://github.com/jetsoncontrols/ha-hacs-token-manager/issues",
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_DOWNLOAD_AUTH)

        # 3. Has HACS's token drifted away from ours? (first run, re-auth clobber)
        if hacs_entry.data.get(CONF_TOKEN) != pat:
            _LOGGER.info(
                "Injecting the private-repo-capable token into HACS; a Home "
                "Assistant restart is required to apply it"
            )
            self._inject_token(hacs_entry, pat)
            self._restart_pending = True
            self.heal_count += 1

        if self._restart_pending:
            # Token is persisted in HACS's entry but HACS is still running on the
            # old one until a restart. Ask for the restart.
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_RESTART_REQUIRED,
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_RESTART_REQUIRED,
            )
            return {
                "healthy": False,
                "reason": "restart_required",
                "heal_count": self.heal_count,
            }

        # HACS's entry already holds our token and this session started with it
        # -> HACS is running on our token. All good.
        ir.async_delete_issue(self.hass, DOMAIN, ISSUE_RESTART_REQUIRED)
        return {"healthy": True, "reason": "ok", "heal_count": self.heal_count}
