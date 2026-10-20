"""XRD instrument formats. Recognition is by content, not by file name."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from core.dataset import Dataset

KEY = "XRD"


# ------------------------------------------------------------ PowDLL Excel export
def detect_powdll(path: Path) -> float:
    if path.suffix.lower() not in (".xls", ".xlsx"):
        return 0.0
    try:
        df = pd.read_excel(path, header=None, nrows=2)
    except Exception:
        return 0.0
    first = [str(v) for v in df.iloc[0].tolist()]
    if first and first[0].strip().upper() == "X" and any(c.strip().endswith("(Y)") for c in first[1:]):
        return 1.0
    return 0.0


def read_powdll(path: Path) -> list[Dataset]:
    """PowDLL Excel export: column 1 = 2theta, the others = intensity of each sample."""
    df = pd.read_excel(path, header=None)
    names = [str(v).strip() for v in df.iloc[0].tolist()]
    data = df.iloc[1:].apply(pd.to_numeric, errors="coerce")
    x = data.iloc[:, 0].to_numpy(float)
    out = []
    for j in range(1, data.shape[1]):
        y = data.iloc[:, j].to_numpy(float)
        ok = ~(np.isnan(x) | np.isnan(y))
        if not ok.any():
            continue
        name = re.sub(r"\s*\(Y\)\s*$", "", names[j]) or f"Sample {j}"
        out.append(Dataset(KEY, name, x[ok], y[ok], path))
    return out
