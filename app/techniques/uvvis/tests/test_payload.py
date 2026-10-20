"""The UV-Vis payload is the contract with origin_build.py, which runs inside Origin.

These tests check that every key origin_build.py reads is present and well formed, without Origin.
"""
import json
import math

import numpy as np

from core import origin_bridge as ob
from techniques.uvvis import TECHNIQUE
from techniques.uvvis import readers as rd

OPTS = {"ref_nm": 1000.0, "a_max": 3.0, "n": 0.5, "tauc": True}


def roundtrip(payload):
    """What origin_build.py will actually see: json.dumps in the app, json.load in Origin."""
    return json.loads(json.dumps(payload))


def test_payload_contract(agilent_file, jasco_file):
    datasets = rd.read_agilent_sd(agilent_file) + rd.read_jasco(jasco_file)
    for d in datasets:
        d.meta["d_nm"] = 400.0
    p = roundtrip(ob.build_payload(TECHNIQUE, datasets, None, OPTS))

    assert p["kind"] == "ABS" and p["ref_nm"] == 1000.0 and p["save_path"] == ""
    assert len(p["groups"]) == 2                       # two different wavelength grids -> X1, X2
    assert set(p["tauc"]) >= {"exponent", "has_thickness", "label", "urbach_max"}
    assert p["tauc"]["has_thickness"] is True
    names = []
    for g in p["groups"]:
        nx = len(g["x"])
        for s in g["series"]:
            names.append(s["name"])
            for key in ("y", "y_norm", "y_corr", "T", "lam"):
                assert len(s[key]) == nx, key
            assert s["lam"] == g["x"]
            assert math.isfinite(s["base_value"])
            t = s["tauc"]
            for key in ("e", "alpha", "ty", "ln_alpha"):
                assert len(t[key]) == nx, key
            lo, hi = t["rows"]                         # 1-based worksheet rows, inclusive
            assert 1 <= lo < hi <= nx
            ulo, uhi = t["urows"]
            assert 1 <= ulo < uhi <= nx
            assert len(s["tauc_range"]) == 2
    assert sorted(names) == sorted(d.name for d in datasets)


def test_without_tauc_only_the_basic_sheets(jasco_file):
    p = roundtrip(ob.build_payload(TECHNIQUE, rd.read_jasco(jasco_file), None, {"ref_nm": 850.0}))
    assert "tauc" not in p
    assert "tauc" not in p["groups"][0]["series"][0]


def test_thickness_is_ignored_unless_every_sample_has_one(agilent_file):
    datasets = rd.read_agilent_sd(agilent_file)
    datasets[0].meta["d_nm"] = 400.0
    p = ob.build_payload(TECHNIQUE, datasets, None, OPTS)
    assert p["tauc"]["has_thickness"] is False
    assert all(s["d_nm"] is None for g in p["groups"] for s in g["series"])


def test_series_stay_matched_to_their_dataset(agilent_file):
    """Duplicate names must not swap data between samples (matched by identity)."""
    datasets = rd.read_agilent_sd(agilent_file)
    p = ob.build_payload(TECHNIQUE, datasets, None, OPTS)
    for ds, s in zip(datasets, p["groups"][0]["series"]):
        np.testing.assert_allclose(s["y"], ds.y)


def test_material_edge_settings_reach_the_auto_range(agilent_file):
    datasets = rd.read_agilent_sd(agilent_file)[:1]
    p = ob.build_payload(TECHNIQUE, datasets, None, {**OPTS, "edge_window_nm": 20.0})
    lo, hi = p["groups"][0]["series"][0]["tauc_range"]
    assert hi - lo == 40.0
