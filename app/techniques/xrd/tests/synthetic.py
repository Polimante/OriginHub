"""Synthetic XRD patterns written in the real instrument formats (no lab data in the repository)."""
from __future__ import annotations

from pathlib import Path

import numpy as np


def xrd_pattern(two_theta: np.ndarray, peaks=((12.7, 300.0), (13.9, 1000.0), (28.1, 500.0)),
                fwhm: float = 0.15, background: float = 50.0) -> np.ndarray:
    sigma = fwhm / 2.3548
    y = np.full_like(two_theta, background)
    for c, h in peaks:
        y += h * np.exp(-0.5 * ((two_theta - c) / sigma) ** 2)
    return y


def write_powdll(path: Path, two_theta: np.ndarray, samples: dict[str, np.ndarray]) -> Path:
    """PowDLL Excel export: first row 'X', '<name> (Y)', ...; one column per sample."""
    import pandas as pd

    cols = {"X": two_theta, **{f"{n} (Y)": y for n, y in samples.items()}}
    df = pd.DataFrame(cols)
    rows = [list(df.columns)] + df.to_numpy().tolist()
    pd.DataFrame(rows).to_excel(path, header=False, index=False)
    return path
