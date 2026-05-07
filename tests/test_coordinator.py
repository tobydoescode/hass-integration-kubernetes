"""Tests for the Kubernetes coordinator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kubernetes.const import (
    DOMAIN,
    KUBERNETES_REQUEST_TIMEOUT,
    RESOURCE_TYPE_DEPLOYMENT,
    RESOURCE_TYPE_STATEFULSET,
)
from custom_components.kubernetes.coordinator import KubernetesCoordinator

from .conftest import MOCK_CONFIG_DATA, MOCK_OPTIONS


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
