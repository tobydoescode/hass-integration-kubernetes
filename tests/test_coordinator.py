"""Tests for the Kubernetes coordinator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kubernetes.const import (
    DOMAIN,
    KUBERNETES_REQUEST_TIMEOUT,
    RESOURCE_TYPE_CLUSTER,
    RESOURCE_TYPE_DEPLOYMENT,
    RESOURCE_TYPE_NODE,
    RESOURCE_TYPE_STATEFULSET,
)
from custom_components.kubernetes.coordinator import KubernetesCoordinator

from .conftest import MOCK_CONFIG_DATA, MOCK_OPTIONS, MOCK_OPTIONS_WITH_NODES


def _make_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a mock config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        options=MOCK_OPTIONS,
        entry_id="test_entry_123",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
async def test_fetch_data(hass: HomeAssistant, mock_k8s_client: MagicMock) -> None:
    """Test that the coordinator fetches deployments and statefulsets."""
    entry = _make_entry(hass)
    coordinator = KubernetesCoordinator(hass, entry)

    await coordinator.async_refresh()

    assert coordinator.data is not None
    assert len(coordinator.data) == 2

    dep_key = ("default", RESOURCE_TYPE_DEPLOYMENT, "web")
    assert dep_key in coordinator.data
    assert coordinator.data[dep_key]["replicas"] == 3
    assert coordinator.data[dep_key]["ready_replicas"] == 3
    assert coordinator.data[dep_key]["available_replicas"] == 3

    # Deployment extra fields
    assert coordinator.data[dep_key]["container_image"] == "nginx:stable-alpine"
    assert coordinator.data[dep_key]["last_restart"] == "2026-01-15T10:30:00Z"
    assert coordinator.data[dep_key]["pod_restart_count"] == 3  # 0 + 2 + 1
    assert coordinator.data[dep_key]["last_restart_reason"] == "OOMKilled"

    sts_key = ("default", RESOURCE_TYPE_STATEFULSET, "db")
    assert sts_key in coordinator.data
    assert coordinator.data[sts_key]["replicas"] == 2
    assert coordinator.data[sts_key]["ready_replicas"] == 2

    # StatefulSet extra fields
    assert coordinator.data[sts_key]["container_image"] == "postgres:16"
    assert coordinator.data[sts_key]["last_restart"] is None
    assert coordinator.data[sts_key]["pod_restart_count"] == 0
    assert coordinator.data[sts_key]["last_restart_reason"] is None


@pytest.mark.asyncio
async def test_fetch_data_uses_request_timeouts(
    hass: HomeAssistant, mock_k8s_client: MagicMock
) -> None:
    """Test that Kubernetes API list calls use explicit request timeouts."""
    entry = _make_entry(hass)
    coordinator = KubernetesCoordinator(hass, entry)

    await coordinator.async_refresh()

    mock_k8s_client.list_namespaced_deployment.assert_called_once_with(
        "default",
        label_selector="homeassistant.io/managed=true",
        _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
    )
    mock_k8s_client.list_namespaced_stateful_set.assert_called_once_with(
        "default",
        label_selector="homeassistant.io/managed=true",
        _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
    )


@pytest.mark.asyncio
async def test_fetch_data_degrades_when_pod_restart_counts_fail(
    hass: HomeAssistant, mock_k8s_client: MagicMock
) -> None:
    """Test that pod list failures do not fail the whole coordinator refresh."""
    mock_k8s_client.core_v1.list_namespaced_pod.side_effect = Exception("pods are forbidden")
    entry = _make_entry(hass)
    coordinator = KubernetesCoordinator(hass, entry)

    await coordinator.async_refresh()

    assert coordinator.data is not None
    dep_key = ("default", RESOURCE_TYPE_DEPLOYMENT, "web")
    assert coordinator.data[dep_key]["ready_replicas"] == 3
    assert coordinator.data[dep_key]["pod_restart_count"] is None
    assert coordinator.data[dep_key]["last_restart_reason"] is None


@pytest.mark.asyncio
async def test_rollout_restart(hass: HomeAssistant, mock_k8s_client: MagicMock) -> None:
    """Test that rollout restart patches the deployment."""
    entry = _make_entry(hass)
    coordinator = KubernetesCoordinator(hass, entry)
    await coordinator.async_refresh()

    await coordinator.async_rollout_restart("default", RESOURCE_TYPE_DEPLOYMENT, "web")

    mock_k8s_client.patch_namespaced_deployment.assert_called_once()
    call_args = mock_k8s_client.patch_namespaced_deployment.call_args
    assert call_args[0][0] == "web"
    assert call_args[0][1] == "default"
    body = call_args[0][2]
    annotations = body["spec"]["template"]["metadata"]["annotations"]
    assert "kubectl.kubernetes.io/restartedAt" in annotations


@pytest.mark.asyncio
async def test_set_replicas(hass: HomeAssistant, mock_k8s_client: MagicMock) -> None:
    """Test that set_replicas patches the deployment scale."""
    entry = _make_entry(hass)
    coordinator = KubernetesCoordinator(hass, entry)
    await coordinator.async_refresh()

    await coordinator.async_set_replicas("default", RESOURCE_TYPE_DEPLOYMENT, "web", 5)

    mock_k8s_client.patch_namespaced_deployment_scale.assert_called_once()
    call_args = mock_k8s_client.patch_namespaced_deployment_scale.call_args
    assert call_args[0][0] == "web"
    assert call_args[0][1] == "default"
    assert call_args[0][2] == {"spec": {"replicas": 5}}


@pytest.mark.asyncio
async def test_set_replicas_statefulset(hass: HomeAssistant, mock_k8s_client: MagicMock) -> None:
    """Test that set_replicas works for statefulsets."""
    entry = _make_entry(hass)
    coordinator = KubernetesCoordinator(hass, entry)
    await coordinator.async_refresh()

    await coordinator.async_set_replicas("default", RESOURCE_TYPE_STATEFULSET, "db", 3)

    mock_k8s_client.patch_namespaced_stateful_set_scale.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_data_with_node_monitoring(
    hass: HomeAssistant, mock_k8s_client: MagicMock
) -> None:
    """Test that node monitoring fetches cluster and node data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        options=MOCK_OPTIONS_WITH_NODES,
        entry_id="test_entry_123",
    )
    entry.add_to_hass(hass)
    coordinator = KubernetesCoordinator(hass, entry)

    await coordinator.async_refresh()

    assert coordinator.data is not None

    # Cluster summary
    cluster_key = ("", RESOURCE_TYPE_CLUSTER, "cluster")
    assert cluster_key in coordinator.data
    assert coordinator.data[cluster_key]["total_nodes"] == 2
    assert coordinator.data[cluster_key]["ready_nodes"] == 2

    # Individual nodes
    node1_key = ("", RESOURCE_TYPE_NODE, "node-1")
    assert node1_key in coordinator.data
    assert coordinator.data[node1_key]["ready"] is True

    node2_key = ("", RESOURCE_TYPE_NODE, "node-2")
    assert node2_key in coordinator.data
    assert coordinator.data[node2_key]["ready"] is True


@pytest.mark.asyncio
async def test_fetch_data_without_node_monitoring(
    hass: HomeAssistant, mock_k8s_client: MagicMock
) -> None:
    """Test that node data is not fetched when node monitoring is disabled."""
    entry = _make_entry(hass)
    coordinator = KubernetesCoordinator(hass, entry)

    await coordinator.async_refresh()

    assert coordinator.data is not None

    cluster_key = ("", RESOURCE_TYPE_CLUSTER, "cluster")
    assert cluster_key not in coordinator.data

    node_key = ("", RESOURCE_TYPE_NODE, "node-1")
    assert node_key not in coordinator.data


@pytest.fixture
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for tests that need full setup."""
    yield


@pytest.mark.asyncio
async def test_stale_device_cleanup(
    hass: HomeAssistant,
    mock_k8s_client: MagicMock,
    auto_enable_custom_integrations,
) -> None:
    """Test that devices are removed when their resources disappear."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        options=MOCK_OPTIONS,
        entry_id="test_entry_123",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Verify "web" device exists
    dev_reg = dr.async_get(hass)
    web_device = dev_reg.async_get_device(
        identifiers={(DOMAIN, "test_entry_123_default/Deployment/web")}
    )
    assert web_device is not None

    # Remove the "web" deployment from the mock
    mock_k8s_client.list_namespaced_deployment.return_value.items = []

    # Refresh coordinator to trigger stale cleanup
    coordinator: KubernetesCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Verify "web" device is removed
    web_device = dev_reg.async_get_device(
        identifiers={(DOMAIN, "test_entry_123_default/Deployment/web")}
    )
    assert web_device is None
