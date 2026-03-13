"""Config flow for the zrok integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BINARY_PATH,
    CONF_RESERVED_TOKEN,
    CONF_SHARE_MODE,
    CONF_TOKEN,
    CONF_TUNNEL_PORT,
    CONF_ZROK_API_ENDPOINT,
    DEFAULT_API_ENDPOINT,
    DEFAULT_HA_PORT,
    DOMAIN,
    SHARE_MODE_EPHEMERAL,
    SHARE_MODE_RESERVED,
)

_LOGGER = logging.getLogger(__name__)


class ZrokConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 1: zrok account token and API endpoint."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            if not token:
                errors[CONF_TOKEN] = "token_required"
            else:
                self._data.update(user_input)
                return await self.async_step_tunnel()

        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Optional(
                    CONF_ZROK_API_ENDPOINT, default=DEFAULT_API_ENDPOINT
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_BINARY_PATH, default=""
                ): selector.TextSelector(),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "docs_url": "https://docs.zrok.io/docs/getting-started/"
            },
        )

    async def async_step_tunnel(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 2: tunnel configuration (share mode, HA port)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="zrok Tunnel",
                data=self._data,
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SHARE_MODE, default=SHARE_MODE_EPHEMERAL
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": SHARE_MODE_EPHEMERAL,
                                "label": "Ephemeral (new URL each start)",
                            },
                            {
                                "value": SHARE_MODE_RESERVED,
                                "label": "Reserved (persistent URL)",
                            },
                        ]
                    )
                ),
                vol.Optional(
                    CONF_RESERVED_TOKEN, default=""
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Optional(
                    CONF_TUNNEL_PORT, default=DEFAULT_HA_PORT
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=65535,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="tunnel",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ZrokOptionsFlow:
        return ZrokOptionsFlow(config_entry)


class ZrokOptionsFlow(config_entries.OptionsFlow):
    """Handle options updates."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._entry.options or self._entry.data

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SHARE_MODE,
                    default=current.get(CONF_SHARE_MODE, SHARE_MODE_EPHEMERAL),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": SHARE_MODE_EPHEMERAL, "label": "Ephemeral"},
                            {"value": SHARE_MODE_RESERVED, "label": "Reserved"},
                        ]
                    )
                ),
                vol.Optional(
                    CONF_RESERVED_TOKEN,
                    default=current.get(CONF_RESERVED_TOKEN, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Optional(
                    CONF_TUNNEL_PORT,
                    default=current.get(CONF_TUNNEL_PORT, DEFAULT_HA_PORT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=65535,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )