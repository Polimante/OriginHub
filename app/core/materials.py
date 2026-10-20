"""Material profiles: analysis defaults per material, in plain TOML files (no code needed).

app/materials/<name>.toml:
    name = "FAPbI3"
    description = "..."
    references = ["https://doi.org/..."]
    [uvvis]                    # one table per technique (Technique.material_section)
    baseline_nm = 1000
    ...
Each technique declares the keys it accepts (Technique.material_schema); unknown keys
or out-of-range values are errors, so a typo in a contributed profile fails the tests.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

MATERIALS_DIR = Path(__file__).resolve().parent.parent / "materials"


@dataclass
class Material:
    name: str
    description: str = ""
    references: list[str] = field(default_factory=list)
    sections: dict[str, dict] = field(default_factory=dict)     # technique section -> values
    source: Path | None = None

    def for_technique(self, technique) -> dict:
        """The technique's defaults overridden by this profile's values."""
        return {**technique.material_defaults, **self.sections.get(technique.material_section, {})}


class MaterialError(ValueError):
    pass


def check_value(key: str, value, rule: tuple):
    """rule: ("number", lo, hi) | ("choice", [options]) | ("text",)"""
    kind = rule[0]
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MaterialError(f"{key}: expected a number, got {value!r}")
        if not rule[1] <= value <= rule[2]:
            raise MaterialError(f"{key}: {value} outside [{rule[1]}, {rule[2]}]")
        return float(value)
    if kind == "choice":
        if value not in rule[1]:
            raise MaterialError(f"{key}: {value!r} is not one of {rule[1]}")
        return value
    if kind == "text":
        if not isinstance(value, str):
            raise MaterialError(f"{key}: expected text")
        return value
    raise MaterialError(f"{key}: unknown rule {rule!r}")


def parse(data: dict, techniques, source: Path | None = None) -> Material:
    """Validates a profile against the techniques' schemas."""
    sections = {t.material_section: t for t in techniques if t.material_section}
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise MaterialError("'name' is required")
    refs = data.get("references", [])
    if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
        raise MaterialError("'references' must be a list of strings")
    mat = Material(name.strip(), str(data.get("description", "")), refs, {}, source)
    for key, value in data.items():
        if key in ("name", "description", "references"):
            continue
        if key not in sections:
            raise MaterialError(f"unknown section or key {key!r} (known sections: {sorted(sections)})")
        if not isinstance(value, dict):
            raise MaterialError(f"[{key}] must be a table")
        schema = sections[key].material_schema
        out = {}
        for k, v in value.items():
            if k not in schema:
                raise MaterialError(f"[{key}] unknown key {k!r} (known: {sorted(schema)})")
            out[k] = check_value(f"[{key}] {k}", v, schema[k])
        mat.sections[key] = out
    return mat


def load_materials(techniques, folder: Path = MATERIALS_DIR) -> tuple[list[Material], dict[str, str]]:
    """All valid profiles (Generic first, then by name) and the errors of the invalid ones."""
    mats, errors = [], {}
    for f in sorted(folder.glob("*.toml")):
        try:
            with open(f, "rb") as fh:
                mats.append(parse(tomllib.load(fh), techniques, f))
        except (OSError, tomllib.TOMLDecodeError, MaterialError) as ex:
            errors[f.name] = str(ex)
    names = [m.name.lower() for m in mats]
    for n in {n for n in names if names.count(n) > 1}:
        errors[n] = f"material name {n!r} used by more than one file"
    mats.sort(key=lambda m: (m.name != "Generic", m.name.lower()))
    return mats, errors
