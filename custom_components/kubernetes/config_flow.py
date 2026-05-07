"""Config flow for the Kubernetes integration."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import voluptuous as vol
import yaml
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import (
    CONF_KUBECONFIG,
    CONF_LABEL_SELECTOR,
    CONF_NAMESPACES,
    CONF_NODE_MONITORING,
    CONF_SCAN_INTERVAL,
    DEFAULT_LABEL_SELECTOR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_KUBECONFIG): TextSelector(
            TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)
        ),
    }
)

STEP_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAMESPACES, default=""): str,
        vol.Optional(CONF_LABEL_SELECTOR, default=DEFAULT_LABEL_SELECTOR): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=600)
        ),
        vol.Optional(CONF_NODE_MONITORING, default=False): bool,
    }
)

FILE_REF_KEYS = ("certificate-authority", "client-certificate", "client-key")


def _validate_kubeconfig(kubeconfig_text: str) -> tuple[dict, str | None]:
    """Parse and validate kubeconfig. Returns (parsed_dict, error_key)."""
    try:
        config_dict = yaml.safe_load(kubeconfig_text)
    except yaml.YAMLError:
        return {}, "invalid_kubeconfig"

    if not isinstance(config_dict, dict):
        return {}, "invalid_kubeconfig"

    # Check for file path references instead of embedded data
    for cluster in config_dict.get("clusters", []):
        cluster_data = cluster.get("cluster", {})
        for key in FILE_REF_KEYS:
            if key in cluster_data:
                return {}, "file_references"

    for user in config_dict.get("users", []):
        user_data = user.get("user", {})
        for key in FILE_REF_KEYS:
            if key in user_data:
                return {}, "file_references"

    return config_dict, None


def _test_connection(config_dict: dict) -> str | None:
    """Test connection to the Kubernetes cluster. Returns error key or None."""
    from kubernetes import client as k8s_client
    from kubernetes.config import new_client_from_config_dict

    try:
        api_client = new_client_from_config_dict(config_dict)
        try:
            v1 = k8s_client.VersionApi(api_client)
            v1.get_code()
        finally:
            api_client.close()
    except Exception:
        _LOGGER.exception("Failed to connect to Kubernetes cluster")
        return "cannot_connect"
    return None


def _cluster_unique_id(config_dict: dict) -> str:
    """Derive a unique ID from the cluster server URL."""
    clusters = config_dict.get("clusters", [])
    server = clusters[0].get("cluster", {}).get("server", "") if clusters else "unknown"
    return hashlib.sha256(server.encode()).hexdigest()[:12]


class KubernetesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kubernetes."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._config_dict: dict = {}
        self._kubeconfig_text: str = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the kubeconfig input step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            kubeconfig_text = user_input[CONF_KUBECONFIG]
            config_dict, error = _validate_kubeconfig(kubeconfig_text)

            if error:
                errors["base"] = error
            else:
                # Test connection in executor (kubernetes client is sync)
                conn_error = await self.hass.async_add_executor_job(_test_connection, config_dict)
                if conn_error:
                    errors["base"] = conn_error
                else:
                    self._config_dict = config_dict
                    self._kubeconfig_text = kubeconfig_text

                    unique_id = _cluster_unique_id(config_dict)
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    return await self.async_step_options()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the options step."""
        if user_input is not None:
            return self.async_create_entry(
                title="Kubernetes",
                data={CONF_KUBECONFIG: self._kubeconfig_text},
                options={
                    CONF_NAMESPACES: user_input.get(CONF_NAMESPACES, ""),
                    CONF_LABEL_SELECTOR: user_input.get(
                        CONF_LABEL_SELECTOR, DEFAULT_LABEL_SELECTOR
                    ),
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    CONF_NODE_MONITORING: user_input.get(CONF_NODE_MONITORING, False),
                },
            )

        return self.async_show_form(
            step_id="options",
            data_schema=STEP_OPTIONS_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow."""
        return KubernetesOptionsFlow(config_entry)


class KubernetesOptionsFlow(OptionsFlow):
    """Handle options flow for Kubernetes."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_NAMESPACES,
                    default=current.get(CONF_NAMESPACES, ""),
                ): str,
                vol.Optional(
                    CONF_LABEL_SELECTOR,
                    default=current.get(CONF_LABEL_SELECTOR, DEFAULT_LABEL_SELECTOR),
                ): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=600)),
                vol.Optional(
                    CONF_NODE_MONITORING,
                    default=current.get(CONF_NODE_MONITORING, False),
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
