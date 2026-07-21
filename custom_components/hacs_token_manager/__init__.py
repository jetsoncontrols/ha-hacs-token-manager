"""HACS Private Token Manager.

Keeps HACS authenticated with a GitHub token that can read your private
repositories, so private custom repositories install/update through the normal
HACS UI. It writes the token into HACS's config entry (with HACS's own reload
listener suppressed, so HACS is never disturbed) and asks for a restart to
apply it, and it authenticates HACS's file downloads so private-repo content
can actually be fetched. See coordinator.py and hacs_patch.py for the why.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import TokenManagerCoordinator
from .hacs_patch import async_patch_hacs_download

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR]

type TokenManagerConfigEntry = ConfigEntry[TokenManagerCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TokenManagerConfigEntry) -> bool:
    """Set up from a config entry."""
    # Make HACS authenticate its GitHub file downloads (private-repo content).
    async_patch_hacs_download()

    coordinator = TokenManagerCoordinator(hass, entry)
    # First refresh performs the initial token check + injection into HACS.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TokenManagerConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
