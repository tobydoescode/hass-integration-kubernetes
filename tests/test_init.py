"""Tests for Kubernetes integration setup, unload, diagnostics, and repairs."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.issue_registry import async_get as async_get_issue_registry
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kubernetes.const import (
    CONF_NODE_MONITORING,
    DEFAULT_LABEL_SELECTOR,
    DOMAIN,
)
from custom_components.kubernetes.diagnostics import async_get_config_entry_diagnostics

from .conftest import MOCK_CONFIG_DATA, MOCK_OPTIONS


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
async def test_setup_and_unload_entry(hass, mock_k8s_client):
    """Test full setup and unload lifecycle."""
    entry = make_entry(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.entry_id in hass.data[DOMAIN]

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_setup_entry_fails_when_cluster_unreachable(hass):
    """Test setup retries when cluster cannot be reached."""
    entry = make_entry(hass)

    with patch(
        "custom_components.kubernetes.coordinator.KubernetesCoordinator._fetch_data",
        side_effect=Exception("Connection refused"),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.asyncio
async def test_diagnostics(hass, mock_k8s_client):
    """Test diagnostics returns expected structure."""
    entry = make_entry(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["config"]["kubeconfig"] == "**REDACTED**"
    assert diag["config"]["namespaces"] == "default"
    assert diag["config"]["label_selector"] == DEFAULT_LABEL_SELECTOR
    assert diag["connection"]["api_client_initialized"] is True
    assert len(diag["resources"]) == 2


@pytest.mark.asyncio
async def test_repair_created_after_repeated_failures(hass, mock_k8s_client):
    """Test repair issue created after 3 consecutive failures."""
    entry = make_entry(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]

    with patch.object(coordinator, "_fetch_data", side_effect=Exception("timeout")):
        for _ in range(3):
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()

    issue_registry = async_get_issue_registry(hass)
    issue = issue_registry.async_get_issue(DOMAIN, f"cluster_unreachable_{entry.entry_id}")
    assert issue is not None
    assert issue.translation_key == "cluster_unreachable"


@pytest.mark.asyncio
async def test_repair_cleared_on_recovery(hass, mock_k8s_client):
    """Test repair issue cleared when cluster recovers."""
    entry = make_entry(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]

    with patch.object(coordinator, "_fetch_data", side_effect=Exception("timeout")):
        for _ in range(3):
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()

    issue_registry = async_get_issue_registry(hass)
    assert (
        issue_registry.async_get_issue(DOMAIN, f"cluster_unreachable_{entry.entry_id}") is not None
    )

    await coordinator._async_update_data()

    assert issue_registry.async_get_issue(DOMAIN, f"cluster_unreachable_{entry.entry_id}") is None


@pytest.mark.asyncio
async def test_migrate_v1_1_to_v1_2_adds_node_monitoring(hass, mock_k8s_client):
    """Test migration adds node_monitoring=False to existing entries."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Kubernetes",
        data=MOCK_CONFIG_DATA,
        unique_id="abc123",
        options={
            "namespaces": "default",
            "label_selector": "homeassistant.io/managed=true",
            "scan_interval": 30,
        },
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 2
    assert entry.options[CONF_NODE_MONITORING] is False
