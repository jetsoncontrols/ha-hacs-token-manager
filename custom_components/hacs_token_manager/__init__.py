"""HACS Private Token Manager.

Keeps HACS authenticated with a GitHub token that can read your private
repositories, so private custom repositories install/update through the normal
HACS UI. It does this without patching HACS: it writes the token into HACS's
config entry and reloads it -- public Home Assistant APIs only.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import TokenManagerCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR]

type TokenManagerConfigEntry = ConfigEntry[TokenManagerCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TokenManagerConfigEntry) -> bool:
    """Set up from a config entry."""
    coordinator = TokenManagerCoordinator(hass, entry)
    # First refresh performs the initial token check + injection into HACS.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TokenManagerConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
