"""Finds the newest Origin, prepares the common payload and opens Origin running the technique's script."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

from core.dataset import Dataset, x_signature

ORIGIN_COMMON = Path(__file__).resolve().parent.parent / "origin_side" / "origin_common.py"
# ASCII-only folder: Origin's command line does not handle accented paths well
WORK = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OriginHub"

LAUNCHER = '''PAYLOAD = r"{payload}"
import sys
sys.path.insert(0, r"{run_dir}")
for _m in ("origin_common", "origin_build"):
    sys.modules.pop(_m, None)            # never reuse modules from a previous export
import origin_common
origin_common.run(PAYLOAD)
'''


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


def ordered(payload: dict, datasets: list[Dataset]) -> list[Dataset]:
    """Datasets in the same order as the series grouped by X (matched by identity, not ==)."""
    order: list[Dataset] = []
    for g in payload["groups"]:
        for s in g["series"]:
            order.append(next(d for d in datasets
                              if d.name == s["name"] and all(d is not o for o in order)))
    return order


def build_payload(technique, datasets: list[Dataset], save_path: Path | None,
                  options: dict | None = None, template: str = "PadraoLinha") -> dict:
    """Common keys (kind, groups, template, save_path) + the technique's own keys."""
    payload = {"kind": technique.key, "groups": group_by_x(datasets), "template": template,
               "save_path": str(save_path) if save_path else ""}
    technique.build_payload(payload, datasets, options or {})
    return payload


# ------------------------------------------------------------ open Origin
def prepare_run(payload: dict, technique) -> tuple[Path, Path]:
    """Writes the run folder: payload JSON, origin_common.py, origin_build.py and the launcher.

    Returns (launcher script, log file). Only this technique's script is copied, so an
    error in another technique cannot affect this export.
    """
    stamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = WORK / f"run_{payload['kind']}_{stamp}"
    n = 1
    while run_dir.exists():                   # two exports in the same second
        n += 1
        run_dir = WORK / f"run_{payload['kind']}_{stamp}_{n}"
    run_dir.mkdir(parents=True)
    pjson = run_dir / "payload.json"
    pjson.write_text(json.dumps(payload), encoding="utf-8")
    shutil.copyfile(ORIGIN_COMMON, run_dir / "origin_common.py")
    shutil.copyfile(technique.origin_script, run_dir / "origin_build.py")
    script = run_dir / "launch.py"
    script.write_text(LAUNCHER.format(payload=pjson, run_dir=run_dir), encoding="utf-8")
    return script, Path(str(pjson) + ".log")


def launch(payload: dict, technique, exe: Path | None = None) -> tuple[subprocess.Popen, Path]:
    exe = exe or latest_origin()
    script, log = prepare_run(payload, technique)
    # single string: Origin reads everything after -rs as LabTalk
    proc = subprocess.Popen(f'"{exe}" -rs run -pyf "{script}"')
    return proc, log
