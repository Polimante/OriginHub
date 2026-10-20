"""UV-Vis absorbance: baseline, transmittance, Tauc band gap and Urbach energy."""
from __future__ import annotations

from pathlib import Path

from core.registry import Reader, Technique

from . import analysis as an
from . import readers
from .payload import build_payload


class UVVis(Technique):
    key = "ABS"
    title = "UV-Vis (ABS)"
    readers = [Reader("JASCO V-780 TXT", readers.detect_jasco, readers.read_jasco),
               Reader("Agilent 8453/8454 ChemStation .SD", readers.detect_agilent_sd, readers.read_agilent_sd)]
    origin_script = Path(__file__).resolve().parent / "origin_build.py"

    material_section = "uvvis"
    material_schema = {
        "baseline_nm": ("number", 200, 3000),
        "transition": ("choice", list(an.TRANSITION_IDS)),
        "a_max": ("number", 0.5, 10),
        "edge_min_nm": ("number", 150, 3000),
        "edge_window_nm": ("number", 5, 300),
    }
    material_defaults = {"baseline_nm": 850.0, "transition": "direct_allowed", "a_max": 3.0,
                         "edge_min_nm": 300.0, "edge_window_nm": 45.0}

    def make_tab(self, main):
        from .tab import UVVisTab
        return UVVisTab(self, main)

    def build_payload(self, payload, datasets, options):
        build_payload(payload, datasets, options)


TECHNIQUE = UVVis()
