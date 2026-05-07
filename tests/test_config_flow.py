"""Tests for the Kubernetes config and options flows."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
