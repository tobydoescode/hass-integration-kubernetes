"""Base entity for the Kubernetes integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from propcache.api import cached_property

from .const import DOMAIN
from .coordinator import KubernetesCoordinator, ResourceKey

CACHED_PROPS = ("device_info", "resource_data", "available", "native_value", "is_on")


def cluster_device_info(entry_id: str) -> DeviceInfo:
    """Return device info for the cluster device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_cluster")},
        name="Kubernetes Cluster",
        manufacturer="Kubernetes",
        model="Cluster",
    )


def node_device_info(entry_id: str, node_name: str) -> DeviceInfo:
    """Return device info for a node device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_node_{node_name}")},
        name=node_name,
        manufacturer="Kubernetes",
        model="Node",
    )


class KubernetesEntity(CoordinatorEntity[KubernetesCoordinator]):  # type: ignore[reportIncompatibleVariableOverride]
    """Base class for Kubernetes entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KubernetesCoordinator,
        resource_key: ResourceKey,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._resource_key = resource_key
        self._namespace, self._kind, self._resource_name = resource_key

    @callback
    def _handle_coordinator_update(self) -> None:
        """Invalidate cached properties and write state."""
        for prop in CACHED_PROPS:
            vars(self).pop(prop, None)
        super()._handle_coordinator_update()

    @property
    def _entry_id(self) -> str:
        return self.coordinator.entry.entry_id

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Return device info for this resource."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, f"{self._entry_id}_{self._namespace}/{self._kind}/{self._resource_name}")
            },
            name=self._resource_name,
            manufacturer="Kubernetes",
            model=self._kind,
            sw_version=self._namespace,
        )

    @cached_property
    def resource_data(self) -> dict[str, Any] | None:
        """Get the current data for this resource."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._resource_key)

    @cached_property
    def available(self) -> bool:  # type: ignore[reportIncompatibleMethodOverride]
        """Return True if the resource exists in the latest data."""
        return super().available and self.resource_data is not None
