"""Tests for Kubernetes entity platforms."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kubernetes.const import (
    CONF_NODE_MONITORING,
    DOMAIN,
)

from .conftest import MOCK_CONFIG_DATA, MOCK_OPTIONS

MOCK_OPTIONS_WITH_NODES = {**MOCK_OPTIONS, CONF_NODE_MONITORING: True}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in tests."""


def make_entry(hass, options: dict | None = None) -> MockConfigEntry:
    """Create and add a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Kubernetes",
        data=MOCK_CONFIG_DATA,
        unique_id="abc123",
        options=options or MOCK_OPTIONS,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
async def test_sensor_ready_pods(hass, mock_k8s_client):
    """Test ready pods sensor reports correct value."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.web_ready_pods")
    assert state is not None
    assert state.state == "3"


@pytest.mark.asyncio
async def test_sensor_desired_replicas(hass, mock_k8s_client):
    """Test desired replicas sensor reports correct value."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.web_desired_replicas")
    assert state is not None
    assert state.state == "3"


@pytest.mark.asyncio
async def test_sensor_available_pods(hass, mock_k8s_client):
    """Test available pods sensor (Deployment only)."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.web_available_pods")
    assert state is not None
    assert state.state == "3"

    # StatefulSet should not have available_pods
    state = hass.states.get("sensor.db_available_pods")
    assert state is None


@pytest.mark.asyncio
async def test_sensor_container_image(hass, mock_k8s_client):
    """Test container image sensor."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.web_container_image")
    assert state is not None
    assert state.state == "nginx:stable-alpine"

    state = hass.states.get("sensor.db_container_image")
    assert state is not None
    assert state.state == "postgres:16"


@pytest.mark.asyncio
async def test_sensor_pod_restart_count(hass, mock_k8s_client):
    """Test pod restart count sensor."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.web_pod_restart_count")
    assert state is not None
    assert state.state == "3"  # 0 + 2 + 1

    state = hass.states.get("sensor.db_pod_restart_count")
    assert state is not None
    assert state.state == "0"


@pytest.mark.asyncio
async def test_sensor_last_restart_reason(hass, mock_k8s_client):
    """Test last restart reason sensor."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.web_last_restart_reason")
    assert state is not None
    assert state.state == "OOMKilled"


@pytest.mark.asyncio
async def test_binary_sensor_rollout_in_progress(hass, mock_k8s_client):
    """Test rollout in progress binary sensor."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # web: updated == ready == replicas, so no rollout
    state = hass.states.get("binary_sensor.web_rollout_in_progress")
    assert state is not None
    assert state.state == STATE_OFF

    # db: same
    state = hass.states.get("binary_sensor.db_rollout_in_progress")
    assert state is not None
    assert state.state == STATE_OFF


@pytest.mark.asyncio
async def test_number_replicas(hass, mock_k8s_client):
    """Test replicas number entity reports current value."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("number.web_replicas")
    assert state is not None
    assert state.state == "3"

    state = hass.states.get("number.db_replicas")
    assert state is not None
    assert state.state == "2"


@pytest.mark.asyncio
async def test_button_rollout_restart(hass, mock_k8s_client):
    """Test rollout restart button exists and can be pressed."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("button.web_rollout_restart")
    assert state is not None

    coordinator = hass.data[DOMAIN][entry.entry_id]
    with patch.object(coordinator, "async_rollout_restart", new_callable=AsyncMock) as mock_restart:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.web_rollout_restart"},
            blocking=True,
        )
        mock_restart.assert_called_once_with("default", "Deployment", "web")


@pytest.mark.asyncio
async def test_device_info_groups_entities(hass, mock_k8s_client):
    """Test all entities for a resource share the same device."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    from homeassistant.helpers.device_registry import async_get as async_get_device_registry

    device_registry = async_get_device_registry(hass)
    devices = [d for d in device_registry.devices.values() if d.name == "web"]
    assert len(devices) == 1
    device = devices[0]
    assert device.manufacturer == "Kubernetes"
    assert device.model == "Deployment"


@pytest.mark.asyncio
async def test_cluster_total_nodes_sensor(hass, mock_k8s_client):
    """Test cluster total nodes sensor reports correct value."""
    entry = make_entry(hass, options=MOCK_OPTIONS_WITH_NODES)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.kubernetes_cluster_total_nodes")
    assert state is not None
    assert state.state == "2"


@pytest.mark.asyncio
async def test_cluster_ready_nodes_sensor(hass, mock_k8s_client):
    """Test cluster ready nodes sensor reports correct value."""
    entry = make_entry(hass, options=MOCK_OPTIONS_WITH_NODES)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.kubernetes_cluster_ready_nodes")
    assert state is not None
    assert state.state == "2"


@pytest.mark.asyncio
async def test_node_ready_binary_sensor(hass, mock_k8s_client):
    """Test node ready binary sensors for each node."""
    entry = make_entry(hass, options=MOCK_OPTIONS_WITH_NODES)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.node_1_ready")
    assert state is not None
    assert state.state == STATE_ON

    state = hass.states.get("binary_sensor.node_2_ready")
    assert state is not None
    assert state.state == STATE_ON


@pytest.mark.asyncio
async def test_no_node_entities_when_monitoring_disabled(hass, mock_k8s_client):
    """Test no cluster/node entities are created when node monitoring disabled."""
    entry = make_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.kubernetes_cluster_total_nodes") is None
    assert hass.states.get("sensor.kubernetes_cluster_ready_nodes") is None
    assert hass.states.get("binary_sensor.node_1_ready") is None
    assert hass.states.get("binary_sensor.node_2_ready") is None
