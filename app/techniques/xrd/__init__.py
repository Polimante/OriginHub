"""XRD patterns: raw and min-max normalized, as stacked lines in Origin.

This is the smallest technique: copy this folder as a starting point for a new one
(see CONTRIBUTING.md, "Adding a technique").
"""
from __future__ import annotations

from pathlib import Path

from core.registry import Reader, Technique

from . import readers


class XRD(Technique):
    key = "XRD"
    title = "XRD"
    readers = [Reader("PowDLL Excel export", readers.detect_powdll, readers.read_powdll)]
    origin_script = Path(__file__).resolve().parent / "origin_build.py"

    def make_tab(self, main):
        from .tab import XRDTab
        return XRDTab(self, main)

    def build_payload(self, payload, datasets, options):
        if len(payload["groups"]) > 1:
            # XRD goes into a single stacked graph
            raise ValueError("The XRD samples have different 2theta axes; export them separately.")


TECHNIQUE = XRD()
