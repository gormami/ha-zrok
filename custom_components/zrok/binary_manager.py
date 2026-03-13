"""Manages downloading and verifying the zrok binary."""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import stat
import tarfile
import tempfile

import aiohttp

from .const import ARCH_MAP, ZROK_BINARY_NAME, ZROK_RELEASE_API, ZROK_RELEASE_BASE

_LOGGER = logging.getLogger(__name__)


def _detect_arch() -> str | None:
    """Return the zrok release architecture suffix for the current machine."""
    machine = platform.machine()
    bits = 64 if platform.architecture()[0] == "64bit" else 32
    return ARCH_MAP.get((machine, bits))


async def _get_latest_version(session: aiohttp.ClientSession) -> str:
    """Fetch the latest zrok release version tag from the GitHub API.

    Returns a version string like '1.1.11' (leading 'v' stripped).
    """
    headers = {"Accept": "application/vnd.github+json"}
    async with session.get(
        ZROK_RELEASE_API,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()

    tag = data.get("tag_name", "")
    if not tag:
        raise RuntimeError("Could not determine latest zrok version from GitHub API.")

    # Strip leading 'v' if present (e.g. 'v1.1.11' -> '1.1.11')
    return tag.lstrip("v")


async def ensure_binary(binary_dir: str) -> str:
    """Ensure the zrok binary exists, downloading it if necessary.

    Returns the absolute path to the binary.
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
    path = os.path.join(binary_dir, ZROK_BINARY_NAME)

    if os.path.isfile(path) and os.access(path, os.X_OK):
        _LOGGER.debug("zrok binary already present at %s", path)
        return path

    # mkstemp guarantees tmp_path is always defined before the try block,
    # preventing UnboundLocalError in the finally clause.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".tar.gz")
    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: resolve the latest version number dynamically
            version = await _get_latest_version(session)
            _LOGGER.info("Latest zrok version: %s", version)

            # Step 2: build the correctly versioned tarball URL
            # e.g. .../download/v1.1.11/zrok_1.1.11_linux_amd64.tar.gz
            tarball = f"zrok_{version}_{arch}.tar.gz"
            url = f"{ZROK_RELEASE_BASE}/v{version}/{tarball}"
            _LOGGER.info("Downloading zrok from %s", url)

            # Step 3: stream download into temp file
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                resp.raise_for_status()
                with os.fdopen(tmp_fd, "wb") as tmp:
                    tmp_fd = None  # fd is now owned by the file object
                    async for chunk in resp.content.iter_chunked(65536):
                        tmp.write(chunk)

        # Step 4: extract in executor to avoid blocking the event loop
        await asyncio.get_event_loop().run_in_executor(
            None, _extract_binary, tmp_path, binary_dir
        )
    finally:
        if tmp_fd is not None:
            os.close(tmp_fd)  # close raw fd if os.fdopen() was never reached
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not os.path.isfile(path):
        raise RuntimeError("zrok binary not found after extraction.")

    # Ensure the binary is executable
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    _LOGGER.info("zrok binary ready at %s", path)
    return path


def _extract_binary(tar_path: str, dest_dir: str) -> None:
    """Extract the zrok binary from a tarball (blocking — run in executor)."""
    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.name.endswith(ZROK_BINARY_NAME) and member.isfile():
                member.name = ZROK_BINARY_NAME  # flatten any directory prefix
                tf.extract(member, dest_dir)
                return
    raise RuntimeError(
        f"Could not find '{ZROK_BINARY_NAME}' inside the downloaded archive."
    )