"""Fixtures for Kubernetes integration tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from custom_components.kubernetes.const import (
    CONF_KUBECONFIG,
    CONF_LABEL_SELECTOR,
    CONF_NAMESPACES,
    CONF_SCAN_INTERVAL,
    DEFAULT_LABEL_SELECTOR,
    DEFAULT_SCAN_INTERVAL,
)

MOCK_KUBECONFIG = """
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://127.0.0.1:6443
    certificate-authority-data: dGVzdA==
  name: test-cluster
contexts:
- context:
    cluster: test-cluster
    user: test-user
  name: test-context
current-context: test-context
users:
- name: test-user
  user:
    client-certificate-data: dGVzdA==
    client-key-data: dGVzdA==
"""

MOCK_CONFIG_DATA = {CONF_KUBECONFIG: MOCK_KUBECONFIG}
MOCK_OPTIONS = {
    CONF_NAMESPACES: "default",
    CONF_LABEL_SELECTOR: DEFAULT_LABEL_SELECTOR,
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
}


def _make_container(image: str) -> MagicMock:
    """Create a mock container spec."""
    container = MagicMock()
    container.image = image
    return container


def _make_pod(
    restart_counts: list[int],
    last_termination: dict | None = None,
) -> MagicMock:
    """Create a mock Pod with container statuses.

    last_termination: if provided, applied to the first container status.
    Keys: "reason" and "finished_at".
    """
    pod = MagicMock()
    statuses = []
    for i, count in enumerate(restart_counts):
        cs = MagicMock()
        cs.restart_count = count
        if i == 0 and last_termination:
            cs.last_state.terminated.reason = last_termination["reason"]
            cs.last_state.terminated.finished_at = last_termination["finished_at"]
        else:
            cs.last_state.terminated = None
        statuses.append(cs)
    pod.status.container_statuses = statuses
    return pod


def _make_deployment(name: str, namespace: str, replicas: int, ready: int, available: int):
    """Create a mock Deployment object."""
    dep = MagicMock()
    dep.metadata.name = name
    dep.metadata.namespace = namespace
    dep.spec.replicas = replicas
    dep.status.ready_replicas = ready
    dep.status.available_replicas = available
    dep.status.updated_replicas = ready
    dep.spec.template.spec.containers = [_make_container("nginx:stable-alpine")]
    dep.spec.template.metadata.annotations = {
        "kubectl.kubernetes.io/restartedAt": "2026-01-15T10:30:00Z"
    }
    dep.spec.selector.match_labels = {"app": "web"}
    return dep


def _make_statefulset(name: str, namespace: str, replicas: int, ready: int):
    """Create a mock StatefulSet object."""
    sts = MagicMock()
    sts.metadata.name = name
    sts.metadata.namespace = namespace
    sts.spec.replicas = replicas
    sts.status.ready_replicas = ready
    sts.status.updated_replicas = ready
    sts.spec.template.spec.containers = [_make_container("postgres:16")]
    sts.spec.template.metadata.annotations = {}
    sts.spec.selector.match_labels = {"app": "db"}
    return sts


@pytest.fixture
def mock_k8s_client() -> Generator[MagicMock]:
    """Mock the Kubernetes client."""
    mock_api_client = MagicMock()
    mock_apps_v1 = MagicMock()
    mock_core_v1 = MagicMock()
    mock_apps_v1.core_v1 = mock_core_v1

    with (
        patch(
            "kubernetes.config.new_client_from_config_dict",
            return_value=mock_api_client,
        ),
        patch(
            "kubernetes.client.AppsV1Api",
            return_value=mock_apps_v1,
        ),
        patch(
            "kubernetes.client.CoreV1Api",
            return_value=mock_core_v1,
        ),
    ):
        # Default: one deployment, one statefulset
        dep_list = MagicMock()
        dep_list.items = [_make_deployment("web", "default", 3, 3, 3)]
        mock_apps_v1.list_namespaced_deployment.return_value = dep_list

        sts_list = MagicMock()
        sts_list.items = [_make_statefulset("db", "default", 2, 2)]
        mock_apps_v1.list_namespaced_stateful_set.return_value = sts_list

        # Mock pod lists for restart count
        web_pods = MagicMock()
        web_pods.items = [
            _make_pod([0]),
            _make_pod(
                [2],
                last_termination={
                    "reason": "OOMKilled",
                    "finished_at": datetime(2026, 1, 15, 10, 25, 0, tzinfo=UTC),
                },
            ),
            _make_pod([1]),
        ]

        db_pods = MagicMock()
        db_pods.items = [_make_pod([0]), _make_pod([0])]

        def _list_pods(namespace, label_selector="", **kwargs):
            if "app=web" in label_selector:
                return web_pods
            if "app=db" in label_selector:
                return db_pods
            return MagicMock(items=[])

        mock_core_v1.list_namespaced_pod.side_effect = _list_pods

        yield mock_apps_v1
