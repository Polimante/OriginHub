"""The payload is the contract between the app and build.py (which runs inside Origin).

These tests check that every key build.py reads is present and well formed, without Origin.
"""
import json
import math
import py_compile

import numpy as np
import pytest

import origin_bridge as ob
import parsers
from parsers import ABS, XRD

ABS_OPTS = {"ref_nm": 1000.0, "a_max": 3.0, "n": 0.5, "tauc": True}


def roundtrip(payload):
    """What build.py will actually see: json.dumps in the app, json.load in Origin."""
    return json.loads(json.dumps(payload))


def test_abs_payload_contract(agilent_file, jasco_file):
    datasets = parsers.load(agilent_file) + parsers.load(jasco_file)
    for d in datasets:
        d.meta["d_nm"] = 400.0
    p = roundtrip(ob.build_payload(ABS, datasets, None, abs_opts=ABS_OPTS))

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


def test_thickness_is_ignored_unless_every_sample_has_one(agilent_file):
    datasets = parsers.load(agilent_file)
    datasets[0].meta["d_nm"] = 400.0
    p = ob.build_payload(ABS, datasets, None, abs_opts=ABS_OPTS)
    assert p["tauc"]["has_thickness"] is False
    assert all(s["d_nm"] is None for g in p["groups"] for s in g["series"])


def test_series_stay_matched_to_their_dataset(agilent_file):
    """Duplicate names must not swap data between samples (matched by identity)."""
    datasets = parsers.load(agilent_file)
    p = ob.build_payload(ABS, datasets, None, abs_opts=ABS_OPTS)
    for ds, s in zip(datasets, p["groups"][0]["series"]):
        np.testing.assert_allclose(s["y"], ds.y)


def test_xrd_payload(powdll_file):
    p = roundtrip(ob.build_payload(XRD, parsers.load(powdll_file), None))
    (g,) = p["groups"]
    for s in g["series"]:
        assert min(s["y_norm"]) == 0.0 and max(s["y_norm"]) == 1.0
        assert len(s["y"]) == len(g["x"])


def test_xrd_with_different_axes_is_refused(powdll_file):
    a, b = parsers.load(powdll_file)
    b.x = b.x[:-10]
    b.y = b.y[:-10]
    with pytest.raises(ValueError, match="different 2theta"):
        ob.build_payload(XRD, [a, b], None)


def test_launch_writes_a_runnable_script(monkeypatch, tmp_path, jasco_file):
    """launch() must write the JSON and a build script with PAYLOAD on top, and call Origin once."""
    calls = []
    monkeypatch.setattr(ob, "WORK", tmp_path / "work")
    monkeypatch.setattr(ob.subprocess, "Popen", lambda cmd: calls.append(cmd) or "proc")
    payload = ob.build_payload(ABS, parsers.load(jasco_file), None, abs_opts={"ref_nm": 850.0})
    proc, log = ob.launch(payload, exe=tmp_path / "Origin64.exe")

    (cmd,) = calls
    assert isinstance(cmd, str)                      # one string: a list double-escapes the quotes
    assert cmd.startswith(f'"{tmp_path / "Origin64.exe"}" -rs run -pyf "')
    script = next((tmp_path / "work").glob("build_ABS_*.py"))
    first = script.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith('PAYLOAD = r"') and first.endswith('.json"')
    py_compile.compile(str(script), doraise=True)
    assert json.loads(next((tmp_path / "work").glob("ABS_*.json")).read_text(encoding="utf-8"))["kind"] == "ABS"
    assert str(log).endswith(".json.log")


def test_find_origins_parses_install_folders(monkeypatch, tmp_path):
    for name in ("Origin2018", "Origin2025b", "OriginPro 2023", "NotOrigin"):
        (tmp_path / "OriginLab" / name).mkdir(parents=True)
        (tmp_path / "OriginLab" / name / "Origin64.exe").write_text("")
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        monkeypatch.setenv(var, str(tmp_path))
    found = ob.find_origins()
    assert [v for v, _ in found] == ["2025b", "2023", "2018"]
    assert ob.latest_origin().parent.name == "Origin2025b"
