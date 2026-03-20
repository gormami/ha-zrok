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

from .const import (
    ARCH_MAP,
    ARCH_MAP_STATIC,
    STATIC_RELEASE_REPO,
    ZROK_BINARY_NAME,
    ZROK_RELEASE_API,
    ZROK_RELEASE_BASE,
)

_LOGGER = logging.getLogger(__name__)


def _detect_arch() -> str | None:
    """Return the zrok release architecture suffix for the current machine."""
    machine = platform.machine()
    bits = 64 if platform.architecture()[0] == "64bit" else 32
    return ARCH_MAP.get((machine, bits))


def _detect_static_arch() -> str | None:
    """Return the static build architecture suffix for the current machine."""
    machine = platform.machine()
    bits = 64 if platform.architecture()[0] == "64bit" else 32
    return ARCH_MAP_STATIC.get((machine, bits))


def _detect_libc() -> str:
    """Detect whether the system uses glibc or musl.

    Returns 'glibc', 'musl', or 'unknown'.
    """
    try:
        import subprocess
        result = subprocess.run(
            ["ldd", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (result.stdout + result.stderr).lower()
        if "musl" in output:
            return "musl"
        if "gnu" in output or "glibc" in output or "free software" in output:
            return "glibc"
    except Exception:
        pass

    # Fallback: check for musl's dynamic linker
    for musl_ld in (
        "/lib/ld-musl-x86_64.so.1",
        "/lib/ld-musl-aarch64.so.1",
        "/lib/ld-musl-armhf.so.1",
    ):
        if os.path.exists(musl_ld):
            return "musl"

    # Fallback: check /etc/os-release for Alpine
    try:
        with open("/etc/os-release") as f:
            if "alpine" in f.read().lower():
                return "musl"
    except OSError:
        pass

    return "unknown"


async def _get_latest_zrok_version(session: aiohttp.ClientSession) -> str:
    """Fetch the latest upstream zrok version from the GitHub API.

    Returns a bare version string like '1.1.11' (no leading 'v').
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
        raise RuntimeError(
            "Could not determine latest zrok version from GitHub API."
        )
    return tag.lstrip("v")


async def _get_latest_static_version(session: aiohttp.ClientSession) -> str | None:
    """Fetch the latest static build version from the ha-zrok releases.

    Returns a bare version string like '1.1.11', or None if not found.
    """
    url = f"https://api.github.com/repos/{STATIC_RELEASE_REPO}/releases/latest"
    headers = {"Accept": "application/vnd.github+json"}
    try:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status == 404:
                return None
            resp.raise_for_status()
            data = await resp.json()
        # Tag format: zrok-static-v1.1.11
        tag = data.get("tag_name", "")
        if tag.startswith("zrok-static-v"):
            return tag.removeprefix("zrok-static-v")
    except Exception as err:
        _LOGGER.debug("Could not fetch static release info: %s", err)
    return None


async def ensure_binary(binary_dir: str) -> str:
    """Ensure the zrok binary exists, downloading it if necessary.

    Strategy:
      1. If binary already exists and is executable, use it.
      2. Detect libc type (glibc vs musl/Alpine).
      3. On musl: attempt to download a static build from ha-zrok releases.
         If no static build exists yet, raise a clear error.
      4. On glibc: download the official upstream release tarball.

    Returns the absolute path to the binary.
    """
    arch = _detect_arch()
    _LOGGER.debug(
        "Architecture detection: machine=%s bits=%s arch=%s",
        platform.machine(),
        platform.architecture()[0],
        arch,
    )
    if not arch:
        raise RuntimeError(
            f"Unsupported architecture: {platform.machine()} "
            f"({platform.architecture()[0]}). "
            "Please install zrok manually and set the binary path."
        )

    os.makedirs(binary_dir, exist_ok=True)
    path = os.path.join(binary_dir, ZROK_BINARY_NAME)
    _LOGGER.debug("zrok binary expected at: %s (dir exists: %s)", path, os.path.isdir(binary_dir))

    if os.path.isfile(path) and os.access(path, os.X_OK):
        _LOGGER.debug("zrok binary already present at %s", path)
        return path

    _LOGGER.debug(
        "Binary not present or not executable (exists: %s, executable: %s)",
        os.path.isfile(path),
        os.access(path, os.X_OK),
    )
    libc = _detect_libc()
    _LOGGER.info("Detected libc: %s", libc)

    async with aiohttp.ClientSession() as session:
        if libc == "musl":
            return await _download_static(session, path, binary_dir)
        else:
            return await _download_upstream(session, path, binary_dir, arch)


async def _download_static(
    session: aiohttp.ClientSession,
    path: str,
    binary_dir: str,
) -> str:
    """Download a statically linked binary from ha-zrok GitHub releases."""
    static_arch = _detect_static_arch()
    if not static_arch:
        raise RuntimeError(
            f"No static zrok build available for architecture: {platform.machine()}. "
            "Please install zrok manually and set the binary path."
        )

    version = await _get_latest_static_version(session)
    if not version:
        raise RuntimeError(
            "No static zrok builds found in the ha-zrok releases yet. "
            "The build workflow may still be running for the first time. "
            "Check https://github.com/gormami/ha-zrok/releases and try again, "
            "or install zrok manually and set the binary_path option."
        )

    tarball = f"zrok_{version}_linux_{static_arch}_static.tar.gz"
    url = (
        f"https://github.com/{STATIC_RELEASE_REPO}/releases/download"
        f"/zrok-static-v{version}/{tarball}"
    )
    _LOGGER.info(
        "Downloading static zrok v%s for %s from %s", version, static_arch, url
    )
    return await _fetch_and_extract(session, url, path, binary_dir)


async def _download_upstream(
    session: aiohttp.ClientSession,
    path: str,
    binary_dir: str,
    arch: str,
) -> str:
    """Download the official upstream glibc-linked tarball."""
    version = await _get_latest_zrok_version(session)
    tarball = f"zrok_{version}_{arch}.tar.gz"
    url = f"{ZROK_RELEASE_BASE}/v{version}/{tarball}"
    _LOGGER.info(
        "Downloading upstream zrok v%s for %s from %s", version, arch, url
    )
    return await _fetch_and_extract(session, url, path, binary_dir)


async def _fetch_and_extract(
    session: aiohttp.ClientSession,
    url: str,
    binary_path: str,
    binary_dir: str,
) -> str:
    """Download a tarball from url and extract the zrok binary to binary_dir."""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".tar.gz")
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            resp.raise_for_status()
            with os.fdopen(tmp_fd, "wb") as tmp:
                tmp_fd = None  # fd now owned by file object
                async for chunk in resp.content.iter_chunked(65536):
                    tmp.write(chunk)

        await asyncio.get_running_loop().run_in_executor(
            None, _extract_binary, tmp_path, binary_dir
        )
    finally:
        if tmp_fd is not None:
            os.close(tmp_fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not os.path.isfile(binary_path):
        raise RuntimeError("zrok binary not found after extraction.")

    st = os.stat(binary_path)
    os.chmod(binary_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    _LOGGER.info("zrok binary ready at %s", binary_path)
    return binary_path


def _extract_binary(tar_path: str, dest_dir: str) -> None:
    """Extract the zrok binary from a tarball (blocking — run in executor)."""
    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.name.endswith(ZROK_BINARY_NAME) and member.isfile():
                member.name = ZROK_BINARY_NAME  # flatten directory prefix
                tf.extract(member, dest_dir, filter="fully_trusted")
                return
    raise RuntimeError(
        f"Could not find '{ZROK_BINARY_NAME}' inside the downloaded archive."
    )