"""Manages downloading and verifying the zrok binary."""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import stat
import tempfile

import aiohttp

from .const import ARCH_MAP, DEFAULT_BINARY_DIR, ZROK_BINARY_NAME, ZROK_RELEASE_BASE

_LOGGER = logging.getLogger(__name__)


def _detect_arch() -> str | None:
    """Return the zrok release architecture suffix for the current machine."""
    machine = platform.machine()
    bits = 64 if platform.architecture()[0] == "64bit" else 32
    return ARCH_MAP.get((machine, bits))


def _binary_path(binary_dir: str) -> str:
    return os.path.join(binary_dir, ZROK_BINARY_NAME)


async def ensure_binary(binary_dir: str = DEFAULT_BINARY_DIR) -> str:
    """Ensure the zrok binary exists, downloading it if necessary.

    Returns the path to the binary.
    Raises RuntimeError if the architecture is unsupported or download fails.
    """
    arch = _detect_arch()
    if not arch:
        raise RuntimeError(
            f"Unsupported architecture: {platform.machine()} "
            f"({platform.architecture()[0]}). "
            "Please install zrok manually and set the binary path."
        )

    os.makedirs(binary_dir, exist_ok=True)
    path = _binary_path(binary_dir)

    if os.path.isfile(path) and os.access(path, os.X_OK):
        _LOGGER.debug("zrok binary already present at %s", path)
        # Optionally validate version here in the future
        return path

    tarball = f"zrok_{arch}.tar.gz"
    url = f"{ZROK_RELEASE_BASE}/{tarball}"
    _LOGGER.info("Downloading zrok from %s", url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                resp.raise_for_status()
                with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                    tmp_path = tmp.name
                    async for chunk in resp.content.iter_chunked(65536):
                        tmp.write(chunk)

        # Extract in executor to avoid blocking the event loop
        await asyncio.get_event_loop().run_in_executor(
            None, _extract_binary, tmp_path, binary_dir
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not os.path.isfile(path):
        raise RuntimeError("zrok binary not found after extraction.")

    # Make executable
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    _LOGGER.info("zrok binary ready at %s", path)
    return path


def _extract_binary(tar_path: str, dest_dir: str) -> None:
    """Extract the zrok binary from a tarball (blocking, run in executor)."""
    import tarfile

    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.name.endswith(ZROK_BINARY_NAME) and member.isfile():
                member.name = ZROK_BINARY_NAME  # flatten path
                tf.extract(member, dest_dir)
                return
    raise RuntimeError(f"Could not find '{ZROK_BINARY_NAME}' inside the downloaded archive.")