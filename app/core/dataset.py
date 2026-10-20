"""The data contract shared by every technique: one Dataset per sample, validated on load."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass(eq=False)
class Dataset:
    kind: str                 # key of the technique that read it ("ABS", "XRD", ...)
    name: str                 # sample name
    x: np.ndarray
    y: np.ndarray
    source: Path
    meta: dict = field(default_factory=dict)


# ------------------------------------------------------------- validation
class DataError(ValueError):
    """A reader returned data that the analysis and Origin cannot handle safely."""


def validate(ds: Dataset) -> None:
    """Checks the contract every reader must meet; raises DataError with a readable reason.

    x: 1-D, finite, strictly ascending (the worksheets and fit windows rely on it);
    y: same length as x, no +/-inf, not all NaN (isolated NaN are allowed: Origin shows gaps).
    """
    where = f"{ds.source.name}: sample '{ds.name}'"
    if not ds.name.strip():
        raise DataError(f"{ds.source.name}: empty sample name")
    x, y = np.asarray(ds.x), np.asarray(ds.y)
    if x.ndim != 1 or y.ndim != 1:
        raise DataError(f"{where}: x and y must be 1-D arrays")
    if len(x) != len(y):
        raise DataError(f"{where}: {len(x)} x values but {len(y)} y values")
    if len(x) < 2:
        raise DataError(f"{where}: fewer than 2 points")
    if not np.all(np.isfinite(x)):
        raise DataError(f"{where}: x axis has NaN or infinite values")
    if np.any(np.diff(x) <= 0):
        raise DataError(f"{where}: x axis is not strictly ascending (repeated or unsorted points)")
    if np.any(np.isinf(y)):
        raise DataError(f"{where}: y has infinite values")
    if np.all(np.isnan(y)):
        raise DataError(f"{where}: y has no numeric values")


# ------------------------------------------------------------------ utils
def read_text(path: Path, limit: int | None = None) -> str:
    """Decodes a text file whatever the instrument PC's encoding was."""
    raw = path.read_bytes()[:limit] if limit else path.read_bytes()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def x_signature(ds: Dataset) -> tuple:
    """Key that identifies the X axis (start, end, step, number of points)."""
    step = float(np.median(np.diff(ds.x))) if len(ds.x) > 1 else 0.0
    return (round(float(ds.x[0]), 4), round(float(ds.x[-1]), 4), round(step, 5), len(ds.x))
