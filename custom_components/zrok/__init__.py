"""The zrok integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .binary_manager import ensure_binary
from .const import (
    CONF_BINARY_PATH,
    CONF_EXTRA_SERVICES,
    CONF_RESERVED_TOKEN,
    CONF_SHARE_MODE,
    CONF_TOKEN,
    CONF_TUNNEL_PORT,
    DEFAULT_BINARY_SUBDIR,
    DEFAULT_HA_PORT,
    DOMAIN,
    PLATFORMS,
    SHARE_MODE_EPHEMERAL,
)
from .tunnel_manager import TunnelManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up zrok from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    cfg = {**entry.data, **entry.options}

    token        = cfg[CONF_TOKEN]
    share_mode   = cfg.get(CONF_SHARE_MODE, SHARE_MODE_EPHEMERAL)
    reserved_tok = cfg.get(CONF_RESERVED_TOKEN, "")
    ha_port      = int(cfg.get(CONF_TUNNEL_PORT, DEFAULT_HA_PORT))
    extra_svcs   = cfg.get(CONF_EXTRA_SERVICES, [])

    # Resolve binary dir: use user-supplied path or default to
    # <config_dir>/zrok, resolved via HA's own path helper so it is
    # always consistent between where we write and where we execute.
    binary_dir = cfg.get(CONF_BINARY_PATH) or hass.config.path(DEFAULT_BINARY_SUBDIR)
    _LOGGER.debug(
        "zrok binary_dir resolved to: %s (from config: %r)",
        binary_dir,
        cfg.get(CONF_BINARY_PATH),
    )

    # 1. Ensure the zrok binary is present
    try:
        binary_path = await ensure_binary(binary_dir)
        _LOGGER.debug("zrok binary path: %s", binary_path)
    except Exception as err:
        _LOGGER.error("Could not obtain zrok binary: %s", err)
        raise ConfigEntryNotReady(f"zrok binary unavailable: {err}") from err

    # 2. Create and start the tunnel manager
    manager = TunnelManager(
        binary_path=binary_path,
        token=token,
        share_mode=share_mode,
        ha_port=ha_port,
        extra_services=extra_svcs,
        reserved_token=reserved_tok,
    )

    try:
        await manager.start_all()
    except Exception as err:
        _LOGGER.error("Failed to start zrok tunnels: %s", err)
        raise ConfigEntryNotReady(f"zrok tunnels failed to start: {err}") from err

    hass.data[DOMAIN][entry.entry_id] = manager

    # 3. Forward to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 4. Register options-update listener
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and tear down tunnels."""
    manager: TunnelManager = hass.data[DOMAIN].get(entry.entry_id)
    if manager:
        await manager.stop_all()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)