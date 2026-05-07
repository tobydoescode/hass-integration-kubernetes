"""Sensor platform for the Kubernetes integration."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from propcache.api import cached_property

from .const import (
    CONF_NODE_MONITORING,
    DOMAIN,
    RESOURCE_TYPE_DEPLOYMENT,
    RESOURCE_TYPE_STATEFULSET,
)
from .coordinator import KubernetesCoordinator, ResourceKey
from .entity import KubernetesEntity
from .node import KubernetesClusterReadyNodesSensor, KubernetesClusterTotalNodesSensor


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kubernetes sensors from a config entry."""
    coordinator: KubernetesCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for key in coordinator.data:
        namespace, kind, name = key
        if kind in (RESOURCE_TYPE_DEPLOYMENT, RESOURCE_TYPE_STATEFULSET):
            entities.append(KubernetesReadyPodsSensor(coordinator, key))
            entities.append(KubernetesDesiredReplicasSensor(coordinator, key))
            if kind == RESOURCE_TYPE_DEPLOYMENT:
                entities.append(KubernetesAvailablePodsSensor(coordinator, key))
            entities.append(KubernetesContainerImageSensor(coordinator, key))
            entities.append(KubernetesLastRestartSensor(coordinator, key))
            entities.append(KubernetesPodRestartCountSensor(coordinator, key))
            entities.append(KubernetesLastRestartReasonSensor(coordinator, key))

    if entry.options.get(CONF_NODE_MONITORING, False):
        entry_id = entry.entry_id
        entities.append(KubernetesClusterTotalNodesSensor(coordinator, entry_id))
        entities.append(KubernetesClusterReadyNodesSensor(coordinator, entry_id))

    async_add_entities(entities)


class KubernetesReadyPodsSensor(KubernetesEntity, SensorEntity):
    """Sensor reporting the number of ready pods."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "pods"
    _attr_icon = "mdi:kubernetes"
    _attr_translation_key = "ready_pods"

    def __init__(self, coordinator: KubernetesCoordinator, resource_key: ResourceKey) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, resource_key)
        self._attr_unique_id = (
            f"{self._entry_id}_{self._namespace}_{self._kind}_{self._resource_name}_ready"
        )

    @cached_property
    def native_value(self) -> int | None:
        """Return the number of ready pods."""
        data = self.resource_data
        if data is None:
            return None
        return data.get("ready_replicas", 0)


class KubernetesDesiredReplicasSensor(KubernetesEntity, SensorEntity):
    """Sensor reporting the desired replica count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "pods"
    _attr_icon = "mdi:kubernetes"
    _attr_translation_key = "desired_replicas"

    def __init__(self, coordinator: KubernetesCoordinator, resource_key: ResourceKey) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, resource_key)
        self._attr_unique_id = (
            f"{self._entry_id}_{self._namespace}_{self._kind}_{self._resource_name}_desired"
        )

    @cached_property
    def native_value(self) -> int | None:
        """Return the desired replica count."""
        data = self.resource_data
        if data is None:
            return None
        return data.get("replicas", 0)


class KubernetesAvailablePodsSensor(KubernetesEntity, SensorEntity):
    """Sensor reporting the number of available pods (Deployments only)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "pods"
    _attr_icon = "mdi:kubernetes"
    _attr_translation_key = "available_pods"

    def __init__(self, coordinator: KubernetesCoordinator, resource_key: ResourceKey) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, resource_key)
        self._attr_unique_id = (
            f"{self._entry_id}_{self._namespace}_{self._kind}_{self._resource_name}_available"
        )

    @cached_property
    def native_value(self) -> int | None:
        """Return the number of available pods."""
        data = self.resource_data
        if data is None:
            return None
        return data.get("available_replicas", 0)


class KubernetesContainerImageSensor(KubernetesEntity, SensorEntity):
    """Sensor reporting the container image."""

    _attr_icon = "mdi:docker"
    _attr_translation_key = "container_image"

    def __init__(self, coordinator: KubernetesCoordinator, resource_key: ResourceKey) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, resource_key)
        self._attr_unique_id = (
            f"{self._entry_id}_{self._namespace}_{self._kind}_{self._resource_name}_image"
        )

    @cached_property
    def native_value(self) -> str | None:
        """Return the container image."""
        data = self.resource_data
        if data is None:
            return None
        return data.get("container_image")


class KubernetesLastRestartSensor(KubernetesEntity, SensorEntity):
    """Sensor reporting the last rollout restart time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "last_restart"

    def __init__(self, coordinator: KubernetesCoordinator, resource_key: ResourceKey) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, resource_key)
        self._attr_unique_id = (
            f"{self._entry_id}_{self._namespace}_{self._kind}_{self._resource_name}_last_restart"
        )

    @cached_property
    def native_value(self) -> datetime | None:
        """Return the last restart timestamp."""
        data = self.resource_data
        if data is None:
            return None
        value = data.get("last_restart")
        if value is None:
            return None
        return datetime.fromisoformat(value)


class KubernetesPodRestartCountSensor(KubernetesEntity, SensorEntity):
    """Sensor reporting the total pod restart count."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "restarts"
    _attr_icon = "mdi:restart-alert"
    _attr_translation_key = "pod_restart_count"

    def __init__(self, coordinator: KubernetesCoordinator, resource_key: ResourceKey) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, resource_key)
        self._attr_unique_id = (
            f"{self._entry_id}_{self._namespace}_{self._kind}_{self._resource_name}_restarts"
        )

    @cached_property
    def native_value(self) -> int | None:
        """Return the total pod restart count."""
        data = self.resource_data
        if data is None:
            return None
        return data.get("pod_restart_count", 0)


class KubernetesLastRestartReasonSensor(KubernetesEntity, SensorEntity):
    """Sensor reporting the last container restart reason."""

    _attr_icon = "mdi:alert-circle-outline"
    _attr_translation_key = "last_restart_reason"

    def __init__(self, coordinator: KubernetesCoordinator, resource_key: ResourceKey) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, resource_key)
        self._attr_unique_id = (
            f"{self._entry_id}_{self._namespace}_{self._kind}"
            f"_{self._resource_name}_last_restart_reason"
        )

    @cached_property
    def native_value(self) -> str | None:
        """Return the last restart reason."""
        data = self.resource_data
        if data is None:
            return None
        return data.get("last_restart_reason")
