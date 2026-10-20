"""Update check against GitHub Releases, verified download, and hand-over to the installer.

Only published releases are offered (GitHub's "latest" excludes drafts and pre-releases).
The installer is downloaded over HTTPS from this repository's release assets and its
SHA-256 must match the .sha256 file published with it. Installing replaces the per-user
installation (no administrator rights) and the installer restarts OriginHub.

ORIGINHUB_UPDATE_API (environment) points the check to another URL; it exists only for the
automated update test, which serves a fake release from a local server.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from version import __version__

REPO = "Polimante/OriginHub"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
TRUSTED_PREFIX = f"https://github.com/{REPO}/releases/download/"


class UpdateError(RuntimeError):
    pass


@dataclass
class Release:
    version: str
    notes: str
    page_url: str
    installer_url: str
    installer_name: str
    sha256_url: str
    size: int


def parse_version(v: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", v.strip())
    if not m:
        raise UpdateError(f"not a version number: {v!r}")
    return tuple(int(g) for g in m.groups())


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse_version(remote) > parse_version(local)


def api_url() -> str:
    return os.environ.get("ORIGINHUB_UPDATE_API", API_URL)


def _trusted(url: str) -> bool:
    return url.startswith(TRUSTED_PREFIX) or "ORIGINHUB_UPDATE_API" in os.environ


def parse_release(data: dict) -> Release:
    """GitHub 'latest release' JSON -> Release; the installer and its .sha256 must be attached."""
    version = data.get("tag_name", "").lstrip("v")
    parse_version(version)
    assets = {a.get("name", ""): a for a in data.get("assets", [])}
    name = f"OriginHub-Setup-{version}.exe"
    if name not in assets or name + ".sha256" not in assets:
        raise UpdateError(f"release {version} has no installer attached")
    inst, sha = assets[name], assets[name + ".sha256"]
    for url in (inst["browser_download_url"], sha["browser_download_url"]):
        if not _trusted(url):
            raise UpdateError(f"unexpected download location: {url}")
    return Release(version, data.get("body") or "", data.get("html_url") or RELEASES_PAGE,
                   inst["browser_download_url"], name, sha["browser_download_url"], int(inst.get("size", 0)))


def _open(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": f"OriginHub/{__version__}",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_latest(timeout: float = 10.0) -> Release:
    """Latest published release. Raises UpdateError (offline, rate limit, no installer...)."""
    try:
        with _open(api_url(), timeout) as r:
            data = json.load(r)
    except UpdateError:
        raise
    except Exception as ex:
        raise UpdateError(f"could not reach GitHub ({ex})") from ex
    return parse_release(data)


def check(timeout: float = 10.0) -> Release | None:
    """The latest release if it is newer than this version, else None."""
    rel = fetch_latest(timeout)
    return rel if is_newer(rel.version) else None


# ------------------------------------------------------------ download
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_sha256(text: str, filename: str) -> str:
    """Reads '<hash>  <file name>' (as written by packaging/build.ps1)."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 1 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            if len(parts) == 1 or parts[-1].lstrip("*") == filename:
                return parts[0].lower()
    raise UpdateError("checksum file is not valid")


def download(rel: Release, folder: Path | None = None,
             progress: Callable[[int, int], None] | None = None, timeout: float = 30.0) -> Path:
    """Downloads the installer and checks its SHA-256. Returns the verified file."""
    folder = folder or Path(tempfile.gettempdir()) / "OriginHub-update"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / rel.installer_name
    try:
        with _open(rel.sha256_url, timeout) as r:
            expected = expected_sha256(r.read().decode("ascii", "replace"), rel.installer_name)
        with _open(rel.installer_url, timeout) as r, open(target, "wb") as f:
            total = int(r.headers.get("Content-Length") or rel.size or 0)
            done = 0
            while chunk := r.read(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except UpdateError:
        raise
    except Exception as ex:
        target.unlink(missing_ok=True)
        raise UpdateError(f"download failed ({ex})") from ex
    actual = sha256_of(target)
    if actual != expected:
        target.unlink(missing_ok=True)
        raise UpdateError("the downloaded file is damaged or was altered (SHA-256 mismatch); nothing was installed")
    return target


# ------------------------------------------------------------ install
def can_self_update() -> bool:
    """Only the installed app (PyInstaller build) can replace itself; a source checkout uses git."""
    return bool(getattr(sys, "frozen", False))


def installer_args(installer: Path) -> list[str]:
    # /SILENT shows only a progress bar; /RELAUNCH=1 makes the installer start OriginHub again
    return [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH=1"]


def launch_installer(installer: Path) -> subprocess.Popen:
    """Starts the installer detached; the caller must quit right after."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(installer_args(installer), creationflags=flags, close_fds=True)
