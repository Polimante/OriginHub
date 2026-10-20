"""Setup check: what OriginHub needs outside itself, and what it may fix (always with the user's consent).

- Origin 2021 or newer (needs a license; OriginHub can only point to it, never install it);
- a writable work folder in %LOCALAPPDATA%\\OriginHub (created if missing);
- the optional graph template(s) in Origin's User Files Folder (copied from the app if missing).
Python packages are bundled in the installed app; a source checkout is checked by bootstrap.py.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from core import origin_bridge as ob

MIN_ORIGIN = 2021                       # first version with the embedded Python + originpro
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "resources" / "templates"
ORIGIN_PATHS = "origin_paths.json"      # written by origin_common.run() inside Origin


@dataclass
class Check:
    key: str
    title: str
    status: str                         # "ok" | "warning" | "error"
    detail: str
    fix: str = ""                       # action id for apply_fix(); empty = nothing to do automatically
    fix_label: str = ""


# ------------------------------------------------------------ folders
def documents_folder() -> Path:
    """The user's Documents folder (also when redirected to OneDrive)."""
    if sys.platform == "win32":
        try:
            folder_id = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")     # FOLDERID_Documents
            guid = (ctypes.c_byte * 16).from_buffer_copy(folder_id.bytes_le)
            ptr = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(ptr)) == 0:
                path = Path(ptr.value)
                ctypes.windll.ole32.CoTaskMemFree(ptr)
                return path
        except Exception:
            pass
    return Path.home() / "Documents"


def user_files_folder(work: Path | None = None) -> Path | None:
    """Origin's User Files Folder: as reported by Origin on the last export, else the default location."""
    work = work or ob.WORK
    try:
        known = json.loads((work / ORIGIN_PATHS).read_text(encoding="utf-8")).get("user_files", "")
        if known and Path(known).is_dir():
            return Path(known)
    except (OSError, ValueError):
        pass
    default = documents_folder() / "OriginLab" / "User Files"
    return default if default.is_dir() else None


def bundled_templates() -> list[Path]:
    return sorted(TEMPLATES_DIR.glob("*.otp*")) if TEMPLATES_DIR.is_dir() else []


# ------------------------------------------------------------ checks
def check_origin() -> Check:
    found = ob.find_origins()
    if not found:
        return Check("origin", "Origin", "error",
                     "No Origin installation was found in Program Files\\OriginLab. OriginHub previews data "
                     "without it, but building projects needs Origin or OriginPro 2021 or newer, with a license "
                     "(https://www.originlab.com).")
    version, exe = found[0]
    year = int(version[:4])
    if year < MIN_ORIGIN:
        return Check("origin", "Origin", "error",
                     f"Origin {version} is too old: OriginHub needs 2021 or newer (embedded Python).")
    return Check("origin", "Origin", "ok", f"Origin {version} ({exe})")


def check_work_folder(work: Path | None = None) -> Check:
    work = work or ob.WORK
    try:
        work.mkdir(parents=True, exist_ok=True)
        probe = work / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as ex:
        return Check("work", "Work folder", "error", f"Cannot write to {work} ({ex}).")
    if not str(work).isascii():
        return Check("work", "Work folder", "warning",
                     f"{work} has non-ASCII characters; Origin's command line may not open it.")
    return Check("work", "Work folder", "ok", str(work))


def check_templates(work: Path | None = None) -> Check:
    uff = user_files_folder(work)
    bundled = bundled_templates()
    names = [p.stem for p in bundled] or ["PadraoLinha"]
    if uff is None:
        return Check("templates", "Graph template", "warning",
                     "Origin's User Files Folder was not found (open Origin once). Until then graphs use "
                     "Origin's default line style.")
    missing = [p for p in bundled if not (uff / p.name).exists()]
    if not bundled:
        present = (uff / "PadraoLinha.otpu").exists()
        return Check("templates", "Graph template", "ok" if present else "warning",
                     f"{'Found' if present else 'Not found'}: PadraoLinha in {uff}" +
                     ("" if present else ". Graphs use Origin's default line style."))
    if not missing:
        return Check("templates", "Graph template", "ok", f"{', '.join(names)} in {uff}")
    return Check("templates", "Graph template", "warning",
                 f"Not installed in {uff}: {', '.join(p.stem for p in missing)}. Without it, graphs use "
                 "Origin's default line style.", fix="install_templates", fix_label="Install template")


def run_checks(work: Path | None = None) -> list[Check]:
    out = []
    for fn in (check_origin, lambda: check_work_folder(work), lambda: check_templates(work)):
        try:
            out.append(fn())
        except Exception as ex:                      # a check must never stop the app
            out.append(Check("internal", "Setup check", "warning", f"check failed: {ex}"))
    return out


# ------------------------------------------------------------ fixes
def install_templates(work: Path | None = None) -> list[Path]:
    """Copies the bundled templates that are missing; never overwrites the user's own files."""
    uff = user_files_folder(work)
    if uff is None:
        raise RuntimeError("Origin's User Files Folder was not found; open Origin once and try again.")
    copied = []
    for src in bundled_templates():
        dst = uff / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
            copied.append(dst)
    return copied


def apply_fix(action: str, work: Path | None = None) -> str:
    if action == "install_templates":
        copied = install_templates(work)
        return f"Installed: {', '.join(p.name for p in copied) or 'nothing (already present)'}"
    raise ValueError(f"unknown fix {action!r}")


def env_summary() -> str:
    """One line for bug reports."""
    from version import __version__
    found = ob.find_origins()
    return (f"OriginHub {__version__} ({'installed' if getattr(sys, 'frozen', False) else 'source'}), "
            f"Python {sys.version.split()[0]}, Origin {found[0][0] if found else 'not found'}, "
            f"{os.environ.get('OS', sys.platform)}")
