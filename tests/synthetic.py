"""Synthetic spectra with known answers, written in the real instrument formats.

No laboratory data is stored in the repository: every test file is generated here.
The UV-Vis model is a direct-allowed edge, (alpha E)^2 = K (E - Eg), joined to an
Urbach tail alpha ~ exp(E / E_U) below it. The join point E_j = Eg + E_U/2 is where
d(ln alpha)/dE of the square-root edge equals 1/E_U, so the curve and its log-slope
are continuous.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

HC = 1239.84193  # eV nm


def direct_edge_alpha(e: np.ndarray, eg: float = 1.55, eu: float = 0.020, k: float = 1.0e10) -> np.ndarray:
    """alpha (cm^-1) for photon energies e (eV). With k = 1e10, alpha(1.8 eV) ~ 2.8e4 cm^-1."""
    ej = eg + eu / 2
    edge = np.sqrt(k * np.clip(e - eg, 0, None)) / e
    aj = np.sqrt(k * (ej - eg)) / ej
    tail = aj * np.exp((e - ej) / eu)
    return np.where(e >= ej, edge, tail)


def uvvis_absorbance(lam: np.ndarray, eg: float = 1.55, eu: float = 0.020, d_nm: float = 400.0,
                     offset: float = 0.10, noise: float = 0.0, seed: int = 0) -> np.ndarray:
    """A(lambda) = alpha d / 2.303 + constant offset (+ optional Gaussian noise)."""
    a = direct_edge_alpha(HC / lam, eg, eu) * d_nm * 1e-7 / 2.303 + offset
    if noise:
        a = a + np.random.default_rng(seed).normal(0, noise, lam.size)
    return a


def xrd_pattern(two_theta: np.ndarray, peaks=((12.7, 300.0), (13.9, 1000.0), (28.1, 500.0)),
                fwhm: float = 0.15, background: float = 50.0) -> np.ndarray:
    sigma = fwhm / 2.3548
    y = np.full_like(two_theta, background)
    for c, h in peaks:
        y += h * np.exp(-0.5 * ((two_theta - c) / sigma) ** 2)
    return y


# ------------------------------------------------------------ file writers
def write_jasco(path: Path, lam_desc: np.ndarray, a: np.ndarray, title: str = "Synthetic",
                sample_name: str | None = None) -> Path:
    """JASCO V-780 TXT layout: header, XYDATA (from long to short wavelength), extended info."""
    head = [
        f"TITLE\t{title}", "DATA TYPE\tULTRAVIOLET SPECTRUM", "ORIGIN\tJASCO", "DATE\t26/01/01",
        f"DELTAX\t{lam_desc[1] - lam_desc[0]}", "XUNITS\tNANOMETERS", "YUNITS\tABSORBANCE",
        f"NPOINTS\t{len(lam_desc)}", "XYDATA",
    ]
    body = [f"{x:.4f}\t{y:.6f}" for x, y in zip(lam_desc, a)]
    tail = ["", "##### Extended Information", "[Comments]", f"Sample name\t{sample_name or title}"]
    path.write_text("\n".join(head + body + tail) + "\n", encoding="utf-8")
    return path


def _u(s: str) -> bytes:
    return s.encode("utf-16le")


def _sd_meta(key: str, value: str) -> bytes:
    # UTF-16 key, 2-byte type, 4 bytes, uint16 length, UTF-16 value (as decoded by parsers.read_agilent_sd)
    return _u(key) + b"\x33\x00" + b"\x00" * 4 + struct.pack("<H", len(value)) + _u(value)


def write_agilent_sd(path: Path, spectra: list[tuple[str, float, float, np.ndarray]]) -> Path:
    """ChemStation .SD with one CHPUVObject per (name, start_nm, step_nm, absorbance) tuple."""
    out = bytearray(b"\x0232\x00\rREGISTER FILE\x00" + b"\x00" * 16)
    for name, start, step, a in spectra:
        out += b"\x0b\x00CHPUVObject" + b"\x00" * 8
        out += _sd_meta("SampleName", name) + _sd_meta("Date", "01/01/2026") + _sd_meta("TimeOfDay", "12:00:00")
        out += _sd_meta("InstrId", "SYNTH")
        out += b"\x00" * 6 + _u("Absorbance (AU)") + b"\x00\x00\xff\xff" + struct.pack("<I", len(a))
        out += b"\x00" + struct.pack("<%dd" % len(a), *a)
        out += b"\x00" * 6 + _u("Wavelength (nm)") + b"\x00\x00\xff\xff" + struct.pack("<I", len(a))
        out += b"\x01" + b"\x01" + b"\x00" * 15 + struct.pack("<2d", start, step) + b"\x00" * 8
    path.write_bytes(bytes(out))
    return path


def write_powdll(path: Path, two_theta: np.ndarray, samples: dict[str, np.ndarray]) -> Path:
    """PowDLL Excel export: first row 'X', '<name> (Y)', ...; one column per sample."""
    import pandas as pd

    cols = {"X": two_theta, **{f"{n} (Y)": y for n, y in samples.items()}}
    df = pd.DataFrame(cols)
    rows = [list(df.columns)] + df.to_numpy().tolist()
    pd.DataFrame(rows).to_excel(path, header=False, index=False)
    return path
