"""Finds the newest Origin, prepares the data and opens Origin running build.py."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

import analysis as an
from parsers import ABS, XRD, Dataset, x_signature

HERE = Path(__file__).resolve().parent
BUILDER = HERE / "origin_side" / "build.py"
# ASCII-only folder: Origin's command line does not handle accented paths well
WORK = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OriginHub"


# ------------------------------------------------------------ find Origin
def find_origins() -> list[tuple[str, Path]]:
    """Lists (version, exe) of the installations, newest first."""
    roots = {Path(os.environ.get(v, "")) / "OriginLab"
             for v in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")}
    found = {}
    for root in roots:
        if not root.is_dir():
            continue
        for d in root.iterdir():
            m = re.match(r"Origin(?:Pro)?\s*(\d{4})([a-z]?)$", d.name, re.I)
            if not m:
                continue
            for exe in ("Origin64.exe", "64Bit/Origin64.exe", "Origin95_64.exe", "Origin.exe"):
                if (d / exe).is_file():
                    found[d / exe] = m.group(1) + m.group(2).lower()
                    break
    return sorted(((v, p) for p, v in found.items()), reverse=True)


def latest_origin() -> Path:
    origins = find_origins()
    if not origins:
        raise FileNotFoundError("No Origin installation found in Program Files\\OriginLab.")
    return origins[0][1]


# ------------------------------------------------------------ prepare data
def group_by_x(datasets: list[Dataset]) -> list[dict]:
    """Groups the samples that share the same X axis (start, end, step, n)."""
    groups: OrderedDict[tuple, dict] = OrderedDict()
    for ds in datasets:
        key = x_signature(ds)
        if key not in groups:
            groups[key] = {"x": ds.x.tolist(), "series": []}
        groups[key]["series"].append(_series(ds))
    return list(groups.values())


def _series(ds: Dataset) -> dict:
    y = ds.y.astype(float)
    lo, hi = float(np.nanmin(y)), float(np.nanmax(y))
    span = (hi - lo) or 1.0
    return {"name": ds.name, "y": y.tolist(), "y_norm": ((y - lo) / span).tolist(),
            "comment": ds.source.name}


def build_payload(kind: str, datasets: list[Dataset], save_path: Path | None,
                  template: str = "PadraoLinha", abs_opts: dict | None = None) -> dict:
    groups = group_by_x(datasets)
    payload = {"kind": kind, "groups": groups, "template": template,
               "save_path": str(save_path) if save_path else ""}
    if kind == XRD and len(groups) > 1:
        # XRD goes into a single stacked graph: a different X will become another book later
        raise ValueError("The XRD samples have different 2theta axes; export them separately.")
    if kind == ABS:
        _add_abs(payload, datasets, abs_opts or {})
    return payload


def _add_abs(payload: dict, datasets: list[Dataset], o: dict):
    """Baseline, %T and (optionally) Tauc/Urbach columns and fit windows per sample."""
    ref, a_max = o.get("ref_nm", 850.0), o.get("a_max", 3.0)
    n = o.get("n", 0.5)
    do_tauc = o.get("tauc", False)
    # thickness is used only if every sample has one (otherwise alpha would mix units)
    use_d = do_tauc and all(d.meta.get("d_nm") for d in datasets)
    payload["ref_nm"] = ref
    series = [s for g in payload["groups"] for s in g["series"]]
    for ds, s in zip(_ordered(payload, datasets), series):
        y_corr, v = an.baseline(ds.x, ds.y, ref)
        s["lam"] = ds.x.tolist()
        s["y_corr"] = y_corr.tolist()
        s["T"] = an.transmittance(ds.y).tolist()
        s["base_value"] = v
        if do_tauc:
            rng = ds.meta.get("tauc_range") or an.suggest_range(ds.x, y_corr, ds.y, a_max)
            d_nm = ds.meta.get("d_nm") if use_d else None
            r = an.tauc_analysis(ds.x, ds.y, y_corr, n, d_nm, rng, a_max)
            s["d_nm"] = d_nm
            s["tauc_range"] = [float(rng[0]), float(rng[1])]
            s["tauc"] = {"e": r.e.tolist(), "alpha": r.alpha.tolist(), "ty": r.ty.tolist(),
                         "ln_alpha": r.ln_alpha.tolist(),
                         "rows": list(r.tauc.rows) if r.tauc else None,
                         "urows": list(r.urbach.rows) if r.urbach else None}
    if do_tauc:
        payload["tauc"] = {"exponent": an.EXPONENT_LABEL[n], "has_thickness": use_d,
                           "label": next(k for k, v in an.TRANSITIONS.items() if v == n),
                           "urbach_max": an.URBACH_MAX_MEV}


def _ordered(payload: dict, datasets: list[Dataset]) -> list[Dataset]:
    """Datasets in the same order as the series grouped by X (matched by identity, not ==)."""
    order: list[Dataset] = []
    for g in payload["groups"]:
        for s in g["series"]:
            order.append(next(d for d in datasets
                              if d.name == s["name"] and all(d is not o for o in order)))
    return order


# ------------------------------------------------------------ open Origin
def launch(payload: dict, exe: Path | None = None) -> tuple[subprocess.Popen, Path]:
    exe = exe or latest_origin()
    WORK.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    pjson = WORK / f"{payload['kind']}_{stamp}.json"
    pjson.write_text(json.dumps(payload), encoding="utf-8")

    script = WORK / f"build_{payload['kind']}_{stamp}.py"
    script.write_text(f"PAYLOAD = r\"{pjson}\"\n" + BUILDER.read_text(encoding="utf-8"),
                      encoding="utf-8")
    # single string: Origin reads everything after -rs as LabTalk
    proc = subprocess.Popen(f'"{exe}" -rs run -pyf "{script}"')
    return proc, Path(str(pjson) + ".log")
