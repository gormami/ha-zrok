"""Manages the lifecycle of zrok tunnel processes."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from .const import DEFAULT_HA_PORT, SHARE_MODE_RESERVED

_LOGGER = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s]+\.zrok\.io[^\s]*")


@dataclass
class TunnelInfo:
    port: int
    name: str
    process: Optional[asyncio.subprocess.Process] = field(default=None, repr=False)
    url: str = ""
    running: bool = False
    error: str = ""


class TunnelManager:
    """Manages one or more zrok share processes."""

    def __init__(
        self,
        binary_path: str,
        token: str,
        share_mode: str,
        ha_port: int = DEFAULT_HA_PORT,
        extra_services: list[dict] | None = None,
        reserved_token: str = "",
    ) -> None:
        self._binary = binary_path
        self._token = token
        self._share_mode = share_mode
        self._ha_port = ha_port
        self._extra_services = extra_services or []
        self._reserved_token = reserved_token
        self._tunnels: dict[str, TunnelInfo] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        """Enable zrok env and start all configured tunnels."""
        await self._enable_env()
        services = [{"name": "homeassistant", "port": self._ha_port}] + self._extra_services
        for svc in services:
            await self._start_tunnel(svc["name"], svc["port"])

    async def stop_all(self) -> None:
        """Terminate all tunnel processes and disable the zrok env."""
        for info in self._tunnels.values():
            await self._stop_tunnel(info)
        self._tunnels.clear()
        await self._disable_env()

    @property
    def tunnels(self) -> dict[str, TunnelInfo]:
        return self._tunnels

    def ha_url(self) -> str:
        t = self._tunnels.get("homeassistant")
        return t.url if t else ""

    def is_running(self) -> bool:
        return any(t.running for t in self._tunnels.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_env(self) -> dict[str, str]:
        """Return an environment dict with ZROK_TOKEN set."""
        env = os.environ.copy()
        env["ZROK_TOKEN"] = self._token
        return env

    async def _run(self, *args: str) -> str:
        """Run the zrok binary with the given arguments and return stdout."""
        proc = await asyncio.create_subprocess_exec(
            self._binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._make_env(),
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode not in (0, None):
            raise RuntimeError(
                f"zrok {' '.join(args)} failed (rc={proc.returncode}): "
                f"{stderr.decode().strip()}"
            )
        return stdout.decode().strip()

    async def _enable_env(self) -> None:
        """Run `zrok enable` to register the environment."""
        _LOGGER.debug("Enabling zrok environment")
        try:
            await self._run("enable", self._token)
        except RuntimeError as err:
            if "already enabled" not in str(err).lower():
                _LOGGER.warning("zrok enable: %s", err)

    async def _disable_env(self) -> None:
        """Run `zrok disable` to clean up the environment."""
        _LOGGER.debug("Disabling zrok environment")
        try:
            await self._run("disable")
        except RuntimeError as err:
            _LOGGER.warning("zrok disable: %s", err)

    async def _start_tunnel(self, name: str, port: int) -> None:
        """Start a single `zrok share` process and capture the tunnel URL."""
        info = TunnelInfo(port=port, name=name)
        self._tunnels[name] = info

        cmd = [self._binary, "share", "public", f"localhost:{port}", "--headless"]

        if self._share_mode == SHARE_MODE_RESERVED and self._reserved_token:
            cmd += ["--reserved", self._reserved_token]

        _LOGGER.info("Starting zrok tunnel for %s on port %d", name, port)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=self._make_env(),
            )
        except Exception as err:
            info.error = str(err)
            _LOGGER.error("Failed to launch zrok for %s: %s", name, err)
            return

        info.process = proc
        asyncio.get_running_loop().create_task(self._watch_output(info))

    async def _watch_output(self, info: TunnelInfo) -> None:
        """Read stdout of a tunnel process, extract URL, log errors."""
        assert info.process and info.process.stdout
        try:
            async for raw in info.process.stdout:
                line = raw.decode(errors="replace").strip()
                _LOGGER.debug("[zrok/%s] %s", info.name, line)
                if not info.url:
                    m = URL_RE.search(line)
                    if m:
                        info.url = m.group(0)
                        info.running = True
                        _LOGGER.info(
                            "zrok tunnel %s live at %s", info.name, info.url
                        )
        except Exception as err:
            _LOGGER.error("zrok/%s output reader error: %s", info.name, err)
        finally:
            info.running = False
            rc = await info.process.wait()
            _LOGGER.warning("zrok/%s process exited (rc=%d)", info.name, rc)

    async def _stop_tunnel(self, info: TunnelInfo) -> None:
        """Terminate a tunnel process gracefully."""
        if info.process and info.running:
            _LOGGER.info("Stopping zrok tunnel %s", info.name)
            try:
                info.process.terminate()
                await asyncio.wait_for(info.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                info.process.kill()
            info.running = False