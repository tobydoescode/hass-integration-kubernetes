"""Constants for the Kubernetes integration."""

DOMAIN = "kubernetes"

CONF_KUBECONFIG = "kubeconfig"
CONF_NAMESPACES = "namespaces"
CONF_LABEL_SELECTOR = "label_selector"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 30
DEFAULT_LABEL_SELECTOR = "homeassistant.io/managed=true"
KUBERNETES_REQUEST_TIMEOUT = 10

RESOURCE_TYPE_DEPLOYMENT = "Deployment"
RESOURCE_TYPE_STATEFULSET = "StatefulSet"
