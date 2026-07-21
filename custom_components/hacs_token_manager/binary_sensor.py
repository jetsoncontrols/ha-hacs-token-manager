"""Health binary sensor for HACS Private Token Manager."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TokenManagerConfigEntry
from .const import DOMAIN
from .coordinator import TokenManagerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TokenManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the health binary sensor."""
    async_add_entities([PrivateRepoAccessSensor(entry.runtime_data, entry)])


class PrivateRepoAccessSensor(
    CoordinatorEntity[TokenManagerCoordinator], BinarySensorEntity
):
    """On == HACS currently holds a valid private-repo-capable token."""

    _attr_has_entity_name = True
    _attr_name = "Private repo access"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, coordinator: TokenManagerCoordinator, entry: TokenManagerConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_private_repo_access"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="HACS Private Token Manager",
            manufacturer="Jetson Controls",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return bool(self.coordinator.data.get("healthy"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data or {}
        return {
            "reason": data.get("reason"),
            "heal_count": data.get("heal_count"),
        }
