"""Tests for the Kubernetes config and options flows."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kubernetes.config_flow import _cluster_unique_id, _validate_kubeconfig
from custom_components.kubernetes.const import (
    CONF_KUBECONFIG,
    CONF_LABEL_SELECTOR,
    CONF_NAMESPACES,
    CONF_SCAN_INTERVAL,
    DEFAULT_LABEL_SELECTOR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

from .conftest import MOCK_KUBECONFIG

PATCH_VALIDATE = "custom_components.kubernetes.config_flow._validate_kubeconfig"
PATCH_TEST_CONN = "custom_components.kubernetes.config_flow._test_connection"
PATCH_UNIQUE_ID = "custom_components.kubernetes.config_flow._cluster_unique_id"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in tests."""


@pytest.mark.asyncio
async def test_user_step_creates_entry_on_success(hass):
    """Test successful config flow creates entry."""
    config_dict = {"clusters": [{"cluster": {"server": "https://127.0.0.1:6443"}}]}
    with (
        patch(PATCH_VALIDATE, return_value=(config_dict, None)),
        patch(PATCH_TEST_CONN, return_value=None),
        patch(PATCH_UNIQUE_ID, return_value="abc123"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_KUBECONFIG: MOCK_KUBECONFIG},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "options"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAMESPACES: "default",
            CONF_LABEL_SELECTOR: DEFAULT_LABEL_SELECTOR,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_KUBECONFIG] == MOCK_KUBECONFIG
    assert result["options"][CONF_NAMESPACES] == "default"


@pytest.mark.asyncio
async def test_user_step_shows_invalid_kubeconfig_error(hass):
    """Test invalid kubeconfig shows error."""
    with patch(PATCH_VALIDATE, return_value=({}, "invalid_kubeconfig")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_KUBECONFIG: "not: valid: yaml: ["},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_kubeconfig"}


@pytest.mark.asyncio
async def test_user_step_shows_file_references_error(hass):
    """Test file path references in kubeconfig shows error."""
    with patch(PATCH_VALIDATE, return_value=({}, "file_references")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_KUBECONFIG: MOCK_KUBECONFIG},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "file_references"}


@pytest.mark.asyncio
async def test_user_step_shows_cannot_connect_error(hass):
    """Test connection failure shows error."""
    config_dict = {"clusters": []}
    with (
        patch(PATCH_VALIDATE, return_value=(config_dict, None)),
        patch(PATCH_TEST_CONN, return_value="cannot_connect"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_KUBECONFIG: MOCK_KUBECONFIG},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_user_step_rejects_duplicate_cluster(hass):
    """Test duplicate cluster is rejected."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_KUBECONFIG: MOCK_KUBECONFIG},
        unique_id="abc123",
    ).add_to_hass(hass)

    config_dict = {"clusters": [{"cluster": {"server": "https://127.0.0.1:6443"}}]}
    with (
        patch(PATCH_VALIDATE, return_value=(config_dict, None)),
        patch(PATCH_TEST_CONN, return_value=None),
        patch(PATCH_UNIQUE_ID, return_value="abc123"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_KUBECONFIG: MOCK_KUBECONFIG},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_user_step_shows_form_without_input(hass):
    """Test initial form is shown without user input."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_options_flow_updates_options(hass, mock_k8s_client):
    """Test options flow updates config entry options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_KUBECONFIG: MOCK_KUBECONFIG},
        unique_id="abc123",
        options={
            CONF_NAMESPACES: "default",
            CONF_LABEL_SELECTOR: DEFAULT_LABEL_SELECTOR,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        },
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_NAMESPACES: "kube-system,monitoring",
            CONF_LABEL_SELECTOR: "app=test",
            CONF_SCAN_INTERVAL: 60,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_NAMESPACES] == "kube-system,monitoring"
    assert entry.options[CONF_LABEL_SELECTOR] == "app=test"
    assert entry.options[CONF_SCAN_INTERVAL] == 60


def test_validate_kubeconfig_valid():
    """Test valid kubeconfig passes validation."""
    config, error = _validate_kubeconfig(MOCK_KUBECONFIG)
    assert error is None
    assert isinstance(config, dict)
    assert "clusters" in config


def test_validate_kubeconfig_invalid_yaml():
    """Test invalid YAML returns error."""
    _, error = _validate_kubeconfig("not: valid: yaml: [")
    assert error == "invalid_kubeconfig"


def test_validate_kubeconfig_not_dict():
    """Test non-dict YAML returns error."""
    _, error = _validate_kubeconfig("just a string")
    assert error == "invalid_kubeconfig"


def test_validate_kubeconfig_file_references_in_cluster():
    """Test file path references in clusters are rejected."""
    kubeconfig = """
apiVersion: v1
clusters:
- cluster:
    server: https://127.0.0.1:6443
    certificate-authority: /path/to/ca.crt
  name: test
contexts: []
users: []
"""
    _, error = _validate_kubeconfig(kubeconfig)
    assert error == "file_references"


def test_validate_kubeconfig_file_references_in_users():
    """Test file path references in users are rejected."""
    kubeconfig = """
apiVersion: v1
clusters: []
contexts: []
users:
- name: test
  user:
    client-certificate: /path/to/cert.pem
"""
    _, error = _validate_kubeconfig(kubeconfig)
    assert error == "file_references"


def test_cluster_unique_id():
    """Test unique ID is derived from server URL."""
    config = {"clusters": [{"cluster": {"server": "https://127.0.0.1:6443"}}]}
    uid = _cluster_unique_id(config)
    assert isinstance(uid, str)
    assert len(uid) == 12


def test_cluster_unique_id_no_clusters():
    """Test unique ID with empty clusters falls back to unknown."""
    uid1 = _cluster_unique_id({"clusters": []})
    uid2 = _cluster_unique_id({})
    assert uid1 == uid2
