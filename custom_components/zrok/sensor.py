"""Sensor platform for zrok – exposes tunnel URL and status."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN, ENTITY_STATUS, ENTITY_URL, POLL_INTERVAL
from .tunnel_manager import TunnelInfo, TunnelManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up zrok sensors from a config entry."""
    manager: TunnelManager = hass.data[DOMAIN][entry.entry_id]

    coordinator = ZrokCoordinator(hass, manager)
    await coordinator.async_config_entry_first_refresh()

    entities: list[SensorEntity] = []
    for tunnel_name in manager.tunnels:
        entities.append(ZrokUrlSensor(coordinator, entry, tunnel_name))
        entities.append(ZrokStatusSensor(coordinator, entry, tunnel_name))

    async_add_entities(entities)


class ZrokCoordinator(DataUpdateCoordinator[dict[str, TunnelInfo]]):
    """Polls the TunnelManager for updated tunnel state."""

    def __init__(self, hass: HomeAssistant, manager: TunnelManager) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="zrok tunnel coordinator",
            update_interval=timedelta(seconds=POLL_INTERVAL),
        )
        self._manager = manager

    async def _async_update_data(self) -> dict[str, TunnelInfo]:
        """Return a snapshot of the current tunnel states."""
        return dict(self._manager.tunnels)


class _ZrokBaseSensor(CoordinatorEntity[ZrokCoordinator], SensorEntity):
    """Base class for zrok sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZrokCoordinator,
        entry: ConfigEntry,
        tunnel_name: str,
        suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._tunnel_name = tunnel_name
        self._attr_unique_id = f"{entry.entry_id}_{tunnel_name}_{suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "zrok Tunnel",
            "manufacturer": "OpenZiti",
            "model": "zrok",
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def _tunnel(self) -> TunnelInfo | None:
        return self.coordinator.data.get(self._tunnel_name)


class ZrokUrlSensor(_ZrokBaseSensor):
    """Reports the public tunnel URL for one service."""

    def __init__(
        self,
        coordinator: ZrokCoordinator,
        entry: ConfigEntry,
        tunnel_name: str,
    ) -> None:
        super().__init__(coordinator, entry, tunnel_name, ENTITY_URL)
        self._attr_name = f"{tunnel_name} URL"
        self._attr_icon = "mdi:link-variant"

    @property
    def native_value(self) -> str:
        t = self._tunnel
        return t.url if t else ""

    @property
    def extra_state_attributes(self) -> dict:
        t = self._tunnel
        return {
            "port": t.port if t else None,
            "tunnel_name": self._tunnel_name,
        }


class ZrokStatusSensor(_ZrokBaseSensor):
    """Reports the running status of one tunnel."""

    def __init__(
        self,
        coordinator: ZrokCoordinator,
        entry: ConfigEntry,
        tunnel_name: str,
    ) -> None:
        super().__init__(coordinator, entry, tunnel_name, ENTITY_STATUS)
        self._attr_name = f"{tunnel_name} status"
        self._attr_icon = "mdi:cloud-check-outline"

    @property
    def native_value(self) -> str:
        t = self._tunnel
        if not t:
            return "unknown"
        if t.error:
            return "error"
        return "connected" if t.running else "disconnected"

    @property
    def extra_state_attributes(self) -> dict:
        t = self._tunnel
        return {"error": t.error if t else ""}