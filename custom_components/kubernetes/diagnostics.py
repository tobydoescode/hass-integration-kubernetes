"""Diagnostics support for Kubernetes integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_LABEL_SELECTOR, CONF_NAMESPACES, CONF_SCAN_INTERVAL, DOMAIN
from .coordinator import KubernetesCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: KubernetesCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "config": {
            "kubeconfig": "**REDACTED**",
            "namespaces": entry.options.get(CONF_NAMESPACES, ""),
            "label_selector": entry.options.get(CONF_LABEL_SELECTOR, ""),
            "scan_interval": entry.options.get(CONF_SCAN_INTERVAL),
        },
        "connection": {
            "api_client_initialized": coordinator._api_client is not None,
        },
        "resources": {
            f"{ns}/{kind}/{name}": data
            for (ns, kind, name), data in (coordinator.data or {}).items()
        },
    }
