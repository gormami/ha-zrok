"""Constants for the zrok integration."""

DOMAIN = "zrok"

# Config entry keys
CONF_TOKEN = "token"
CONF_SHARE_MODE = "share_mode"
CONF_RESERVED_TOKEN = "reserved_token"
CONF_TUNNEL_PORT = "tunnel_port"
CONF_EXTRA_SERVICES = "extra_services"
CONF_ZROK_API_ENDPOINT = "zrok_api_endpoint"
CONF_BINARY_PATH = "binary_path"

# Defaults
DEFAULT_HA_PORT = 8123
DEFAULT_API_ENDPOINT = "https://api.zrok.io"
DEFAULT_BINARY_SUBDIR = "zrok"
ZROK_BINARY_NAME = "zrok"

# Platforms
PLATFORMS = ["sensor"]

# zrok GitHub API URL for latest release metadata
ZROK_RELEASE_API = "https://api.github.com/repos/openziti/zrok/releases/latest"

# zrok GitHub release download base URL (version inserted at runtime)
ZROK_RELEASE_BASE = "https://github.com/openziti/zrok/releases/download"

# ha-zrok repo that hosts statically linked builds for musl/Alpine/HAOS
STATIC_RELEASE_REPO = "gormami/ha-zrok"

# Architecture map: (machine, bits) -> upstream zrok release suffix
ARCH_MAP = {
    ("x86_64", 64):  "linux_amd64",
    ("aarch64", 64): "linux_arm64",
    ("armv7l", 32):  "linux_armv7",
    ("armv6l", 32):  "linux_armv6",
}

# Architecture map: (machine, bits) -> static build suffix (from ha-zrok releases)
ARCH_MAP_STATIC = {
    ("x86_64", 64):  "amd64",
    ("aarch64", 64): "arm64",
    ("armv7l", 32):  "armv7",
}

# Entity unique ID suffixes
ENTITY_STATUS = "status"
ENTITY_URL    = "url"

# Update interval for status polling (seconds)
POLL_INTERVAL = 30

# Share modes
SHARE_MODE_RESERVED = "reserved"
SHARE_MODE_EPHEMERAL = "ephemeral"