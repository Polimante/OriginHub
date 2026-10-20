"""File recognition and readers for the raw instrument files.

Each reader returns a list of Dataset objects (one per sample). The file type is
recognized from its content, not from its name.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ABS, XRD, JV, UNKNOWN = "ABS", "XRD", "JV", "?"


@dataclass(eq=False)
class Dataset:
    kind: str                 # ABS, XRD, ...
    name: str                 # sample name
    x: np.ndarray
    y: np.ndarray
    source: Path
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------- detection
def detect(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".sd":
        head = path.read_bytes()[:4096]
        if b"REGISTER FILE" in head and b"CHPUVObject" in head:
            return ABS
    if ext in (".txt", ".csv", ".dat", ".jws"):
        head = _read_text(path, 4000)
        if "XYDATA" in head and ("ULTRAVIOLET" in head or "ABSORBANCE" in head or "JASCO" in head):
            return ABS
    if ext in (".xls", ".xlsx"):
        try:
            df = pd.read_excel(path, header=None, nrows=2)
        except Exception:
            return UNKNOWN
        first = [str(v) for v in df.iloc[0].tolist()]
        if first and first[0].strip().upper() == "X" and any(c.strip().endswith("(Y)") for c in first[1:]):
            return XRD
    return UNKNOWN


def load(path: Path) -> list[Dataset]:
    kind = detect(path)
    if kind == ABS and path.suffix.lower() == ".sd":
        out = read_agilent_sd(path)
    elif kind == ABS:
        out = [read_jasco(path)]
    elif kind == XRD:
        out = read_powdll(path)
    else:
        raise ValueError(f"Unrecognized format: {path.name}")
    for ds in out:
        validate(ds)
    return out


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


# ------------------------------------------------------------------ UV-Vis
def read_jasco(path: Path) -> Dataset:
    """JASCO V-780 TXT: only the (lambda, A) pairs below XYDATA."""
    lines = _read_text(path).splitlines()
    header, xs, ys = {}, [], []
    i = 0
    while i < len(lines) and lines[i].strip() != "XYDATA":
        parts = lines[i].split("\t", 1)
        if len(parts) == 2:
            header[parts[0].strip()] = parts[1].strip()
        i += 1
    for line in lines[i + 1:]:
        parts = line.replace(",", ".").split()
        if len(parts) < 2:
            break                        # end of the numeric block
        try:
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
        except ValueError:
            break

    # the file name wins: users often rename the file after the measurement
    m = re.search(r"^Sample name\t(.*)$", "\n".join(lines), re.M)
    internal = (m.group(1).strip() if m else "") or header.get("TITLE", "")

    x, y = np.array(xs), np.array(ys)
    order = np.argsort(x)                # the instrument writes from 850 down to 400
    return Dataset(ABS, path.stem, x[order], y[order], path,
                   {"sample_name": internal, "date": header.get("DATE", "")})


def read_agilent_sd(path: Path) -> list[Dataset]:
    """ChemStation UV-Vis .SD (Agilent 8453/8454): several spectra in one file.

    Binary format (MFC serialization) with no public documentation; decoded as:
      - each spectrum starts at "CHPUVObject";
      - metadata: UTF-16 key, 2-byte type, 4 bytes, uint16 length, UTF-16 value;
      - "Absorbance (AU)" + 00 00 FF FF + uint32 n + 1 byte + n doubles;
      - "Wavelength (nm)" + 00 00 FF FF + uint32 n + 01 + ... start and step (doubles).
    """
    d = path.read_bytes()
    u = lambda s: s.encode("utf-16le")

    def meta(key, start, stop):
        i = d.find(u(key), start, stop)
        if i < 0:
            return ""
        j = i + len(u(key)) + 6                      # type (2) + 4 bytes
        n = struct.unpack_from("<H", d, j)[0]
        return d[j + 2:j + 2 + 2 * n].decode("utf-16le", "replace").strip() if n < 500 else ""

    def block(label, start, stop):
        i = d.find(u(label), start, stop)
        if i < 0:
            raise ValueError(f"block '{label}' not found")
        e = i + len(u(label))
        if d[e:e + 4] != b"\x00\x00\xff\xff":
            raise ValueError(f"unexpected format after '{label}'")
        return e + 8, struct.unpack_from("<I", d, e + 4)[0]

    starts = [m.start() for m in re.finditer(b"CHPUVObject", d)]
    out, seen = [], {}
    for k, o in enumerate(starts):
        stop = starts[k + 1] if k + 1 < len(starts) else len(d)
        if d.find(u("Absorbance (AU)"), o, stop) < 0:
            continue
        a0, n = block("Absorbance (AU)", o, stop)
        y = np.array(struct.unpack_from("<%dd" % n, d, a0 + 1))
        w0, nw = block("Wavelength (nm)", a0, len(d))
        if d[w0] == 1:                                # implicit axis: start + step
            x = None
            for off in range(w0 + 1, w0 + 48):
                s0, st = struct.unpack_from("<2d", d, off)
                if 100 <= s0 <= 3500 and 0 < st <= 20:
                    x = s0 + st * np.arange(nw)
                    break
            if x is None:
                raise ValueError("wavelength axis not found")
        else:                                         # explicit axis
            x = np.array(struct.unpack_from("<%dd" % nw, d, w0 + 1))
        name = meta("SampleName", o, stop) or f"{path.stem}_{k + 1}"
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:                            # same name measured again
            name = f"{name}_{seen[name]}"
        order = np.argsort(x)
        out.append(Dataset(ABS, name, x[order], y[order], path,
                           {"time": meta("TimeOfDay", o, stop), "date": meta("Date", o, stop),
                            "instrument": meta("InstrId", o, stop)}))
    if not out:
        raise ValueError("no spectrum found in the .SD file")
    return out


# -------------------------------------------------------------------- XRD
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
        out.append(Dataset(XRD, name, x[ok], y[ok], path))
    return out


# ------------------------------------------------------------------ utils
def _read_text(path: Path, limit: int | None = None) -> str:
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
