"""Entity classes for Kubernetes cluster and node monitoring."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from propcache.api import cached_property

from .const import RESOURCE_TYPE_CLUSTER, RESOURCE_TYPE_NODE
from .coordinator import KubernetesCoordinator, ResourceKey
from .entity import cluster_device_info, node_device_info

CACHED_PROPS = ("available", "native_value", "is_on")


class _ClusterNodeEntity(CoordinatorEntity[KubernetesCoordinator]):  # type: ignore[reportIncompatibleVariableOverride]
    """Base class for cluster and node entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KubernetesCoordinator,
        resource_key: ResourceKey,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._resource_key = resource_key
        self._attr_device_info = device_info

    @callback
    def _handle_coordinator_update(self) -> None:
        """Invalidate cached properties and write state."""
        for prop in CACHED_PROPS:
            vars(self).pop(prop, None)
        super()._handle_coordinator_update()

    @property
    def _resource_data(self) -> dict[str, Any] | None:
        """Get the current data for this resource."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._resource_key)

    @cached_property
    def available(self) -> bool:  # type: ignore[reportIncompatibleMethodOverride]
        """Return True if the resource exists in the latest data."""
        return super().available and self._resource_data is not None


class KubernetesClusterTotalNodesSensor(_ClusterNodeEntity, SensorEntity):
    """Sensor reporting the total number of nodes in the cluster."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "nodes"
    _attr_icon = "mdi:server"
    _attr_translation_key = "total_nodes"

    def __init__(self, coordinator: KubernetesCoordinator, entry_id: str) -> None:
        """Initialize the sensor."""
        resource_key: ResourceKey = ("", RESOURCE_TYPE_CLUSTER, "cluster")
        super().__init__(coordinator, resource_key, cluster_device_info(entry_id))
        self._attr_unique_id = f"{entry_id}_cluster_total_nodes"

    @cached_property
    def native_value(self) -> int | None:
        """Return the total number of nodes."""
        data = self._resource_data
        if data is None:
            return None
        return data.get("total_nodes", 0)


class KubernetesClusterReadyNodesSensor(_ClusterNodeEntity, SensorEntity):
    """Sensor reporting the number of ready nodes in the cluster."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "nodes"
    _attr_icon = "mdi:server-security"
    _attr_translation_key = "ready_nodes"

    def __init__(self, coordinator: KubernetesCoordinator, entry_id: str) -> None:
        """Initialize the sensor."""
        resource_key: ResourceKey = ("", RESOURCE_TYPE_CLUSTER, "cluster")
        super().__init__(coordinator, resource_key, cluster_device_info(entry_id))
        self._attr_unique_id = f"{entry_id}_cluster_ready_nodes"

    @cached_property
    def native_value(self) -> int | None:
        """Return the number of ready nodes."""
        data = self._resource_data
        if data is None:
            return None
        return data.get("ready_nodes", 0)


class KubernetesNodeReadyBinarySensor(_ClusterNodeEntity, BinarySensorEntity):
    """Binary sensor indicating whether a node is ready."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:server-network"
    _attr_translation_key = "node_ready"

    def __init__(self, coordinator: KubernetesCoordinator, entry_id: str, node_name: str) -> None:
        """Initialize the binary sensor."""
        resource_key: ResourceKey = ("", RESOURCE_TYPE_NODE, node_name)
        super().__init__(coordinator, resource_key, node_device_info(entry_id, node_name))
        self._attr_unique_id = f"{entry_id}_node_{node_name}_ready"

    @cached_property
    def is_on(self) -> bool | None:
        """Return True if the node is ready."""
        data = self._resource_data
        if data is None:
            return None
        return data.get("ready")
