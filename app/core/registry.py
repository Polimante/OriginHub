"""Technique plugins: discovery, file identification and isolation of failures.

Each sub-package of app/techniques/ is one technique. Its __init__.py exposes
`TECHNIQUE`, an instance of a Technique subclass. A plugin that fails to import or
breaks the interface is recorded in Registry.failures and the others keep working.
"""
from __future__ import annotations

import ast
import importlib
import pkgutil
import re
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from core.dataset import Dataset, validate


@dataclass
class Reader:
    """One instrument file format."""
    name: str                                   # e.g. "JASCO V-780 TXT"
    detect: Callable[[Path], float]             # 0 = not this format ... 1 = certain; from the CONTENT
    read: Callable[[Path], list[Dataset]]       # one Dataset per sample in the file


class Technique:
    """Base class of a characterization technique (one folder in app/techniques/)."""

    key: str = ""              # payload kind and file prefix, e.g. "ABS" (upper case)
    title: str = ""            # tab title, e.g. "UV-Vis (ABS)"
    readers: list[Reader] = []
    origin_script: Path | None = None           # runs inside Origin; must define build(cfg)
    # material profiles (app/materials/*.toml): the [section] this technique reads, the keys it
    # accepts with their rule ("number", lo, hi) | ("choice", [...]) | ("text",), and defaults
    material_section: str = ""
    material_schema: dict[str, tuple] = {}
    material_defaults: dict = {}

    def make_tab(self, main):
        """Returns the QWidget of the tab (usually a core.tab.TechniqueTab subclass)."""
        raise NotImplementedError

    def build_payload(self, payload: dict, datasets: list[Dataset], options: dict) -> None:
        """Adds the technique's own keys to the common payload (in place); may raise ValueError."""


def check_technique(t: Technique) -> None:
    """Raises TypeError/ValueError if a plugin does not meet the interface."""
    if not isinstance(t, Technique):
        raise TypeError("TECHNIQUE must be an instance of core.registry.Technique")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,15}", t.key or ""):
        raise ValueError(f"invalid key {t.key!r}: 2-16 upper-case letters, digits or _")
    if not t.title:
        raise ValueError(f"{t.key}: empty title")
    if not t.readers or not all(isinstance(r, Reader) for r in t.readers):
        raise ValueError(f"{t.key}: needs at least one Reader")
    if not t.origin_script or not Path(t.origin_script).is_file():
        raise ValueError(f"{t.key}: origin_script not found: {t.origin_script}")
    tree = ast.parse(Path(t.origin_script).read_text(encoding="utf-8"))
    if not any(isinstance(n, ast.FunctionDef) and n.name == "build" for n in tree.body):
        raise ValueError(f"{t.key}: {Path(t.origin_script).name} must define build(cfg)")


@dataclass
class Registry:
    techniques: dict[str, Technique] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)      # plugin folder -> error text

    def identify(self, path: Path) -> tuple[Technique, Reader] | None:
        """The reader that recognizes the file with the highest confidence (errors count as 0)."""
        best, score = None, 0.0
        for t in self.techniques.values():
            for r in t.readers:
                try:
                    s = float(r.detect(path))
                except Exception:
                    s = 0.0
                if s > score:
                    best, score = (t, r), s
        return best

    def load(self, path: Path) -> tuple[Technique, list[Dataset]]:
        hit = self.identify(path)
        if not hit:
            raise ValueError(f"Unrecognized format: {path.name}")
        t, r = hit
        out = r.read(path)
        for ds in out:
            ds.kind = t.key
            validate(ds)
        return t, out


def discover(package: str = "techniques") -> Registry:
    reg = Registry()
    pkg = importlib.import_module(package)
    for m in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if not m.ispkg or m.name.startswith("_"):
            continue
        try:
            t = importlib.import_module(f"{package}.{m.name}").TECHNIQUE
            check_technique(t)
            if t.key in reg.techniques:
                raise ValueError(f"key {t.key!r} already used by another technique")
            reg.techniques[t.key] = t
        except Exception:
            reg.failures[m.name] = traceback.format_exc()
    return reg
