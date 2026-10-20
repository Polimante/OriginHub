"""Runs before anything else when OriginHub starts from source: are the Python packages installed?

Standard library only (it runs before numpy/PyQt6 can be imported). If packages are missing,
the user is asked (small Tk dialog, or the console) whether to install them with pip from
requirements.txt. Nothing is installed without a "yes". The installed app bundles everything
and skips this check.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"
# import name -> pip name (as in requirements.txt)
REQUIRED = {"numpy": "numpy", "pandas": "pandas", "openpyxl": "openpyxl", "xlrd": "xlrd",
            "PyQt6": "PyQt6", "pyqtgraph": "pyqtgraph"}
MIN_PYTHON = (3, 11)


def missing_packages(find_spec: Callable = importlib.util.find_spec) -> list[str]:
    return [pip for mod, pip in REQUIRED.items() if find_spec(mod) is None]


def _tk_ask(title: str, text: str) -> bool | None:
    """Yes/no dialog with Tk; None if Tk is not available."""
    try:
        import tkinter
        from tkinter import messagebox
    except Exception:
        return None
    root = tkinter.Tk()
    root.withdraw()
    try:
        return bool(messagebox.askyesno(title, text))
    finally:
        root.destroy()


def _tk_info(title: str, text: str, error: bool = False) -> bool:
    try:
        import tkinter
        from tkinter import messagebox
    except Exception:
        return False
    root = tkinter.Tk()
    root.withdraw()
    (messagebox.showerror if error else messagebox.showinfo)(title, text)
    root.destroy()
    return True


def ask(text: str) -> bool:
    answer = _tk_ask("OriginHub - missing components", text)
    if answer is None:                                   # no Tk: console
        try:
            answer = input(text + " [y/N] ").strip().lower() in ("y", "yes", "s", "sim")
        except EOFError:
            answer = False
    return answer


def tell(text: str, error: bool = False):
    if not _tk_info("OriginHub", text, error):
        print(text, file=sys.stderr)


def pip_install(requirements: Path = REQUIREMENTS) -> tuple[bool, str]:
    proc = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements)],
                          capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]


def ensure_packages(find_spec: Callable = importlib.util.find_spec, asker: Callable[[str], bool] = ask,
                    installer: Callable[[], tuple[bool, str]] = pip_install,
                    teller: Callable[..., None] = tell) -> bool:
    """True when OriginHub can start. Never installs anything without the user's consent."""
    if getattr(sys, "frozen", False):
        return True
    if sys.version_info < MIN_PYTHON:
        teller(f"OriginHub needs Python {'.'.join(map(str, MIN_PYTHON))} or newer "
               f"(this is {sys.version.split()[0]}). Or use the Windows installer from "
               "https://github.com/Polimante/OriginHub/releases", error=True)
        return False
    missing = missing_packages(find_spec)
    if not missing:
        return True
    if not asker("OriginHub needs these Python packages, which are not installed:\n\n"
                 f"    {', '.join(missing)}\n\n"
                 f"Install them now with pip (from {REQUIREMENTS.name})? This needs an internet connection."):
        teller("OriginHub cannot start without: " + ", ".join(missing) +
               f"\n\nInstall them with:\n    {sys.executable} -m pip install -r \"{REQUIREMENTS}\"", error=True)
        return False
    ok, log = installer()
    importlib.invalidate_caches()
    still = missing_packages(find_spec)
    if not ok or still:
        teller("Installation failed" + (f" (still missing: {', '.join(still)})" if still else "") +
               ":\n\n" + log, error=True)
        return False
    return True
