# Home Assistant Kubernetes Integration

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tobydoescode&repository=ha-integration-kubernetes&category=integration)

A [HACS](https://hacs.xyz)-compatible custom integration that exposes Kubernetes Deployments and StatefulSets as Home Assistant devices.

## Features

Each labeled Deployment or StatefulSet becomes an HA device with:

- **Sensors** — ready pods, desired replicas, available pods (Deployments only), container image, last restart time, pod restart count, last restart reason
- **Button** — trigger a rollout restart
- **Number** — set the replica count (0–50)

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations** → **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Install **Kubernetes** and restart Home Assistant

### Manual

Copy the `custom_components/kubernetes` directory into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Kubernetes**
3. Paste your kubeconfig contents (must use embedded certificate data — see [Kubeconfig requirements](#kubeconfig-requirements))
4. Configure:
   - **Namespaces** — comma-separated list, or leave blank for all namespaces
   - **Label selector** — defaults to `homeassistant.io/managed=true`
   - **Polling interval** — how often to poll the Kubernetes API (10–600 seconds, default 30)

After setup, you can change namespaces, label selector, and polling interval via **Settings → Devices & Services → Kubernetes → Configure**.

## Resource discovery

The integration only discovers Deployments and StatefulSets that match the configured label selector. By default, resources must have the label `homeassistant.io/managed=true`:

```bash
kubectl label deployment my-app homeassistant.io/managed=true
kubectl label statefulset my-db homeassistant.io/managed=true
```

## Kubeconfig requirements

The kubeconfig must use **embedded certificate data** (`certificate-authority-data`, `client-certificate-data`, `client-key-data`) rather than file path references. File paths on your local machine won't be accessible from within Home Assistant.

To generate a self-contained kubeconfig:

```bash
kubectl config view --raw --flatten
```

### RBAC

The service account in your kubeconfig needs these minimum permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: homeassistant
rules:
  - apiGroups: ["apps"]
    resources: ["deployments", "deployments/scale", "statefulsets", "statefulsets/scale"]
    verbs: ["get", "list", "patch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["get", "list"]
```

The `nodes` permission is only required when node monitoring is enabled.

## Development

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Task](https://taskfile.dev) — task runner
- [Docker](https://www.docker.com) — for the dev HA instance
- [Kind](https://kind.sigs.k8s.io) — for a local test Kubernetes cluster

### Commands

| Command | Description |
|---|---|
| `task sync` | Install Python dependencies |
| `task lint` | Run ruff linter and format check |
| `task lint:fix` | Auto-fix lint and formatting issues |
| `task test` | Run pytest |
| `task dev` | Start Home Assistant in Docker |
| `task dev:stop` | Stop Home Assistant |
| `task dev:restart` | Restart Home Assistant (after code changes) |
| `task dev:logs` | Tail Home Assistant logs |
| `task kind:create` | Create a Kind cluster and deploy test nginx |
| `task kind:kubeconfig` | Print kubeconfig (rewritten for Docker access) |
| `task kind:delete` | Delete the Kind cluster |

### Testing with Kind

1. **Create the cluster and deploy a test workload:**

   ```bash
   task kind:create
   ```

   This creates a Kind cluster named `ha-test` and deploys a 3-replica nginx Deployment with the `homeassistant.io/managed=true` label.

2. **Start Home Assistant:**

   ```bash
   task dev
   ```

   Open http://localhost:8123 and complete the onboarding.

3. **Get the kubeconfig:**

   ```bash
   task kind:kubeconfig
   ```

   This outputs the Kind kubeconfig with `127.0.0.1` replaced by `host.docker.internal` so the HA container (running in Docker) can reach the Kind API server. Copy the full output.

4. **Add the integration:**

   Go to **Settings → Devices & Services → Add Integration → Kubernetes** and paste the kubeconfig from step 3.

5. **Verify:**

   Go to **Settings → Devices & Services → Kubernetes**. You should see an `nginx` device with:
   - Ready pods: 3
   - Desired replicas: 3
   - Available pods: 3
   - Container image, last restart time, pod restart count, last restart reason sensors
   - A rollout restart button
   - A replica count control

6. **Clean up:**

   ```bash
   task kind:delete
   task dev:stop
   ```
