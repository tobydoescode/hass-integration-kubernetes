"""DataUpdateCoordinator for the Kubernetes integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import yaml
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_KUBECONFIG,
    CONF_LABEL_SELECTOR,
    CONF_NAMESPACES,
    CONF_SCAN_INTERVAL,
    DEFAULT_LABEL_SELECTOR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    KUBERNETES_REQUEST_TIMEOUT,
    RESOURCE_TYPE_DEPLOYMENT,
    RESOURCE_TYPE_STATEFULSET,
)

_LOGGER = logging.getLogger(__name__)

type ResourceKey = tuple[str, str, str]  # (namespace, kind, name)
type ResourceData = dict[str, Any]
type CoordinatorData = dict[ResourceKey, ResourceData]


class KubernetesCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Coordinator to fetch Kubernetes resource data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )

        kubeconfig_text = entry.data[CONF_KUBECONFIG]
        self._config_dict = yaml.safe_load(kubeconfig_text)
        self._api_client = None
        self._apps_v1 = None
        self._core_v1 = None
        self._consecutive_failures: int = 0

    def _ensure_client(self) -> None:
        """Create the Kubernetes API client if not already created."""
        if self._api_client is not None:
            return

        from kubernetes import client as k8s_client
        from kubernetes.config import new_client_from_config_dict

        self._api_client = new_client_from_config_dict(self._config_dict)
        self._apps_v1 = k8s_client.AppsV1Api(self._api_client)
        self._core_v1 = k8s_client.CoreV1Api(self._api_client)

    @property
    def namespaces(self) -> list[str]:
        """Get configured namespaces."""
        ns_str = self.entry.options.get(CONF_NAMESPACES, "")
        return [ns.strip() for ns in ns_str.split(",") if ns.strip()]

    @property
    def label_selector(self) -> str:
        """Get configured label selector."""
        return self.entry.options.get(CONF_LABEL_SELECTOR, DEFAULT_LABEL_SELECTOR)

    async def _async_update_data(self) -> CoordinatorData:
        """Fetch data from Kubernetes."""
        try:
            data = await self.hass.async_add_executor_job(self._fetch_data)
        except Exception as err:
            self._consecutive_failures += 1
            self._maybe_create_repair()
            raise UpdateFailed(f"Error fetching Kubernetes data: {err}") from err
        self._clear_repair()
        return data

    def _maybe_create_repair(self) -> None:
        """Create a repair issue after repeated connection failures."""
        if self._consecutive_failures < 3:
            return
        async_create_issue(
            self.hass,
            DOMAIN,
            f"cluster_unreachable_{self.entry.entry_id}",
            is_fixable=False,
            severity=IssueSeverity.ERROR,
            translation_key="cluster_unreachable",
        )

    def _clear_repair(self) -> None:
        """Clear connection repair issue on successful communication."""
        if self._consecutive_failures > 0:
            self._consecutive_failures = 0
            async_delete_issue(
                self.hass,
                DOMAIN,
                f"cluster_unreachable_{self.entry.entry_id}",
            )

    def _fetch_data(self) -> CoordinatorData:
        """Fetch deployments and statefulsets (sync, runs in executor)."""
        self._ensure_client()
        assert self._apps_v1 is not None
        assert self._core_v1 is not None
        data: CoordinatorData = {}
        namespaces = self.namespaces
        label_selector = self.label_selector

        # Fetch Deployments
        if namespaces:
            for ns in namespaces:
                deps = self._apps_v1.list_namespaced_deployment(
                    ns,
                    label_selector=label_selector,
                    _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
                )
                self._process_deployments(deps.items, data)
        else:
            deps = self._apps_v1.list_deployment_for_all_namespaces(
                label_selector=label_selector,
                _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
            )
            self._process_deployments(deps.items, data)

        # Fetch StatefulSets
        if namespaces:
            for ns in namespaces:
                sts = self._apps_v1.list_namespaced_stateful_set(
                    ns,
                    label_selector=label_selector,
                    _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
                )
                self._process_statefulsets(sts.items, data)
        else:
            sts = self._apps_v1.list_stateful_set_for_all_namespaces(
                label_selector=label_selector,
                _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
            )
            self._process_statefulsets(sts.items, data)

        # Fetch pod restart counts for each resource
        self._fetch_pod_restart_counts(data)

        return data

    def _fetch_pod_restart_counts(self, data: CoordinatorData) -> None:
        """Fetch pod restart counts and last restart reason for each resource."""
        assert self._core_v1 is not None
        for key, resource in data.items():
            namespace = key[0]
            match_labels = resource.get("match_labels", {})
            if not match_labels:
                resource["pod_restart_count"] = 0
                resource["last_restart_reason"] = None
                continue

            label_selector = ",".join(f"{k}={v}" for k, v in match_labels.items())
            try:
                pods = self._core_v1.list_namespaced_pod(
                    namespace,
                    label_selector=label_selector,
                    _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
                )
            except Exception as err:
                _LOGGER.warning(
                    "Could not fetch pod restart metrics for %s/%s/%s: %s",
                    namespace,
                    key[1],
                    key[2],
                    err,
                )
                resource["pod_restart_count"] = None
                resource["last_restart_reason"] = None
                continue

            total_restarts = 0
            latest_reason: str | None = None
            latest_finished: datetime | None = None
            for pod in pods.items:
                for cs in pod.status.container_statuses or []:
                    total_restarts += cs.restart_count
                    terminated = cs.last_state.terminated if cs.last_state else None
                    if (
                        terminated
                        and terminated.reason
                        and terminated.finished_at
                        and (latest_finished is None or terminated.finished_at > latest_finished)
                    ):
                        latest_finished = terminated.finished_at
                        latest_reason = terminated.reason
            resource["pod_restart_count"] = total_restarts
            resource["last_restart_reason"] = latest_reason

    def _process_deployments(self, items: list, data: CoordinatorData) -> None:
        """Process deployment items into coordinator data."""
        for dep in items:
            key: ResourceKey = (
                dep.metadata.namespace,
                RESOURCE_TYPE_DEPLOYMENT,
                dep.metadata.name,
            )
            containers = dep.spec.template.spec.containers or []
            annotations = dep.spec.template.metadata.annotations or {}
            match_labels = dep.spec.selector.match_labels or {}
            data[key] = {
                "replicas": dep.spec.replicas or 0,
                "ready_replicas": dep.status.ready_replicas or 0,
                "available_replicas": dep.status.available_replicas or 0,
                "updated_replicas": dep.status.updated_replicas or 0,
                "container_image": containers[0].image if containers else None,
                "last_restart": annotations.get("kubectl.kubernetes.io/restartedAt"),
                "match_labels": match_labels,
            }

    def _process_statefulsets(self, items: list, data: CoordinatorData) -> None:
        """Process statefulset items into coordinator data."""
        for sts in items:
            key: ResourceKey = (
                sts.metadata.namespace,
                RESOURCE_TYPE_STATEFULSET,
                sts.metadata.name,
            )
            containers = sts.spec.template.spec.containers or []
            annotations = sts.spec.template.metadata.annotations or {}
            match_labels = sts.spec.selector.match_labels or {}
            data[key] = {
                "replicas": sts.spec.replicas or 0,
                "ready_replicas": sts.status.ready_replicas or 0,
                "updated_replicas": sts.status.updated_replicas or 0,
                "container_image": containers[0].image if containers else None,
                "last_restart": annotations.get("kubectl.kubernetes.io/restartedAt"),
                "match_labels": match_labels,
            }

    async def async_rollout_restart(self, namespace: str, kind: str, name: str) -> None:
        """Trigger a rollout restart by patching the pod template annotation."""
        await self.hass.async_add_executor_job(self._rollout_restart, namespace, kind, name)
        await self.async_request_refresh()

    def _rollout_restart(self, namespace: str, kind: str, name: str) -> None:
        """Perform rollout restart (sync, runs in executor)."""
        self._ensure_client()
        assert self._apps_v1 is not None
        now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": now,
                        }
                    }
                }
            }
        }
        if kind == RESOURCE_TYPE_DEPLOYMENT:
            self._apps_v1.patch_namespaced_deployment(
                name,
                namespace,
                body,
                _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
            )
        elif kind == RESOURCE_TYPE_STATEFULSET:
            self._apps_v1.patch_namespaced_stateful_set(
                name,
                namespace,
                body,
                _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
            )

    async def async_set_replicas(self, namespace: str, kind: str, name: str, replicas: int) -> None:
        """Scale a resource to the specified replica count."""
        await self.hass.async_add_executor_job(self._set_replicas, namespace, kind, name, replicas)
        await self.async_request_refresh()

    def _set_replicas(self, namespace: str, kind: str, name: str, replicas: int) -> None:
        """Set replica count (sync, runs in executor)."""
        self._ensure_client()
        assert self._apps_v1 is not None
        body = {"spec": {"replicas": replicas}}
        if kind == RESOURCE_TYPE_DEPLOYMENT:
            self._apps_v1.patch_namespaced_deployment_scale(
                name,
                namespace,
                body,
                _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
            )
        elif kind == RESOURCE_TYPE_STATEFULSET:
            self._apps_v1.patch_namespaced_stateful_set_scale(
                name,
                namespace,
                body,
                _request_timeout=KUBERNETES_REQUEST_TIMEOUT,
            )

    def close(self) -> None:
        """Close the API client."""
        if self._api_client is not None:
            self._api_client.close()
            self._api_client = None
            self._apps_v1 = None
            self._core_v1 = None
