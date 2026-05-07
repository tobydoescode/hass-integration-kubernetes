"""Button platform for the Kubernetes integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, RESOURCE_TYPE_DEPLOYMENT, RESOURCE_TYPE_STATEFULSET
from .coordinator import KubernetesCoordinator, ResourceKey
from .entity import KubernetesEntity

WORKLOAD_TYPES = {RESOURCE_TYPE_DEPLOYMENT, RESOURCE_TYPE_STATEFULSET}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kubernetes buttons from a config entry."""
    coordinator: KubernetesCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        KubernetesRolloutRestartButton(coordinator, key)
        for key in coordinator.data
        if key[1] in WORKLOAD_TYPES
    ]
    async_add_entities(entities)


class KubernetesRolloutRestartButton(KubernetesEntity, ButtonEntity):
    """Button to trigger a rollout restart."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_icon = "mdi:restart"
    _attr_translation_key = "rollout_restart"

    def __init__(self, coordinator: KubernetesCoordinator, resource_key: ResourceKey) -> None:
        """Initialize the button."""
        super().__init__(coordinator, resource_key)
        self._attr_unique_id = (
            f"{self._entry_id}_{self._namespace}_{self._kind}_{self._resource_name}_restart"
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_rollout_restart(
            self._namespace, self._kind, self._resource_name
        )
