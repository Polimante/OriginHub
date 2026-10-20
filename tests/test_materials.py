"""Material profiles: every shipped profile must be valid, and mistakes must be caught."""
import tomllib

import pytest

from core.materials import MATERIALS_DIR, MaterialError, load_materials, parse
from core.registry import discover

TECHS = list(discover().techniques.values())
UV = next(t for t in TECHS if t.material_section == "uvvis")


def test_all_shipped_profiles_are_valid():
    mats, errors = load_materials(TECHS)
    assert not errors, errors
    assert mats[0].name == "Generic"
    assert {"Generic", "FAPbI3"} <= {m.name for m in mats}


@pytest.mark.parametrize("path", sorted(MATERIALS_DIR.glob("*.toml")), ids=lambda p: p.name)
def test_profile_values_cover_the_technique(path):
    with open(path, "rb") as f:
        mat = parse(tomllib.load(f), TECHS, path)
    values = mat.for_technique(UV)
    assert set(values) == set(UV.material_defaults)
    assert values["edge_min_nm"] < values["baseline_nm"]      # the edge search must not start past the baseline


def test_defaults_fill_missing_keys():
    mat = parse({"name": "X", "uvvis": {"baseline_nm": 900}}, TECHS)
    v = mat.for_technique(UV)
    assert v["baseline_nm"] == 900.0
    assert v["transition"] == UV.material_defaults["transition"]


def test_fapbi3_uses_the_agreed_baseline():
    mats, _ = load_materials(TECHS)
    fa = next(m for m in mats if m.name == "FAPbI3")
    assert fa.for_technique(UV)["baseline_nm"] == 1000.0


@pytest.mark.parametrize("data, reason", [
    ({}, "'name' is required"),
    ({"name": "X", "uvvis": {"baseline": 900}}, "unknown key 'baseline'"),
    ({"name": "X", "uvvis": {"baseline_nm": "900"}}, "expected a number"),
    ({"name": "X", "uvvis": {"baseline_nm": 50}}, "outside"),
    ({"name": "X", "uvvis": {"transition": "direct"}}, "is not one of"),
    ({"name": "X", "uv-vis": {}}, "unknown section"),
    ({"name": "X", "references": "doi"}, "list of strings"),
])
def test_mistakes_are_reported(data, reason):
    with pytest.raises(MaterialError, match=reason):
        parse(data, TECHS)


def test_invalid_files_are_skipped_not_fatal(tmp_path):
    (tmp_path / "ok.toml").write_text('name = "Ok"\n')
    (tmp_path / "typo.toml").write_text('name = "Typo"\n[uvvis]\nbaseline = 900\n')
    (tmp_path / "syntax.toml").write_text('name = "Broken\n')
    (tmp_path / "dup.toml").write_text('name = "ok"\n')
    mats, errors = load_materials(TECHS, tmp_path)
    assert {m.name for m in mats} == {"Ok", "ok"}
    assert {"typo.toml", "syntax.toml", "ok"} == set(errors)
