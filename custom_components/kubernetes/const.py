"""Constants for the Kubernetes integration."""

DOMAIN = "kubernetes"

CONF_KUBECONFIG = "kubeconfig"
CONF_NAMESPACES = "namespaces"
CONF_LABEL_SELECTOR = "label_selector"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30
DEFAULT_LABEL_SELECTOR = "homeassistant.io/managed=true"
KUBERNETES_REQUEST_TIMEOUT = 10

CONF_NODE_MONITORING = "node_monitoring"

RESOURCE_TYPE_DEPLOYMENT = "Deployment"
RESOURCE_TYPE_STATEFULSET = "StatefulSet"
RESOURCE_TYPE_NODE = "Node"
RESOURCE_TYPE_CLUSTER = "Cluster"
