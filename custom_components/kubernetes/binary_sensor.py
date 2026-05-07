"""Binary sensor platform for the Kubernetes integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from propcache.api import cached_property

from .const import DOMAIN
from .coordinator import KubernetesCoordinator, ResourceKey
from .entity import KubernetesEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kubernetes binary sensors from a config entry."""
    coordinator: KubernetesCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        KubernetesRolloutInProgressBinarySensor(coordinator, key) for key in coordinator.data
    ]
    async_add_entities(entities)


class KubernetesRolloutInProgressBinarySensor(KubernetesEntity, BinarySensorEntity):
    """Binary sensor indicating whether a rollout is in progress."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:progress-wrench"
    _attr_translation_key = "rollout_in_progress"

    def __init__(self, coordinator: KubernetesCoordinator, resource_key: ResourceKey) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, resource_key)
        self._attr_unique_id = (
            f"{self._entry_id}_{self._namespace}_{self._kind}"
            f"_{self._resource_name}_rollout_in_progress"
        )

    @cached_property
    def is_on(self) -> bool | None:
        """Return True if a rollout is in progress."""
        data = self.resource_data
        if data is None:
            return None
        replicas = data.get("replicas", 0)
        updated = data.get("updated_replicas", 0)
        return updated < replicas
