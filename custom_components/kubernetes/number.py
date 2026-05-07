"""Number platform for the Kubernetes integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Set up Kubernetes number entities from a config entry."""
    coordinator: KubernetesCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [KubernetesReplicasNumber(coordinator, key) for key in coordinator.data]
    async_add_entities(entities)


class KubernetesReplicasNumber(KubernetesEntity, NumberEntity):
    """Number entity to set the replica count."""

    _attr_icon = "mdi:counter"
    _attr_native_min_value = 0
    _attr_native_max_value = 50
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_translation_key = "replicas"

    def __init__(self, coordinator: KubernetesCoordinator, resource_key: ResourceKey) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, resource_key)
        self._attr_unique_id = (
            f"{self._entry_id}_{self._namespace}_{self._kind}_{self._resource_name}_replicas"
        )

    @cached_property
    def native_value(self) -> float | None:
        """Return the current replica count."""
        data = self.resource_data
        if data is None:
            return None
        return data.get("replicas", 0)

    async def async_set_native_value(self, value: float) -> None:
        """Set the replica count."""
        await self.coordinator.async_set_replicas(
            self._namespace, self._kind, self._resource_name, int(value)
        )
