"""UV-Vis processing: baseline, transmittance, Tauc and Urbach.

This module only prepares the columns and picks the fit windows. The official
linear fits (Eg and E_U) are done by Origin, on the same rows.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HC = 1239.84193                       # eV.nm

# label -> n in (alpha h nu)^(1/n)
TRANSITIONS = {
    "Direct allowed (n = 1/2)": 0.5,
    "Direct forbidden (n = 3/2)": 1.5,
    "Indirect allowed (n = 2)": 2.0,
    "Indirect forbidden (n = 3)": 3.0,
}
EXPONENT_LABEL = {0.5: "2", 1.5: "2/3", 2.0: "1/2", 3.0: "1/3"}


# ------------------------------------------------------------ processing
def baseline(x: np.ndarray, y: np.ndarray, ref: float = 850.0, half: float = 2.0) -> tuple[np.ndarray, float]:
    """Subtracts the value at `ref` nm (mean within +/- half nm; if empty, the nearest point)."""
    near = np.abs(x - ref) <= half
    v = float(np.nanmean(y[near])) if near.any() else float(y[np.nanargmin(np.abs(x - ref))])
    return y - v, v


def transmittance(a: np.ndarray) -> np.ndarray:
    return 100.0 * np.power(10.0, -a)


def alpha(a_corr: np.ndarray, d_nm: float | None) -> np.ndarray:
    """alpha = 2.303 A / d (cm^-1). Without thickness: 2.303 A (a.u.) - Eg does not change."""
    return 2.303 * a_corr / (d_nm * 1e-7) if d_nm else 2.303 * a_corr


def tauc_y(e: np.ndarray, alp: np.ndarray, n: float) -> np.ndarray:
    return np.power(np.clip(alp * e, 0, None), 1.0 / n)


# ------------------------------------------------------------ fit windows
def _r2(x, y):
    if len(x) < 3:
        return 0.0
    b, a = np.polyfit(x, y, 1)
    res = y - (a + b * x)
    tot = np.sum((y - y.mean()) ** 2)
    return 1 - np.sum(res ** 2) / tot if tot else 0.0


def _smooth(y, k=5):
    return np.convolve(y, np.ones(k) / k, mode="same") if len(y) > k else y


def _grow(x, y, valid, i0, r2min, minpts, maxpts):
    """Grows a contiguous window around i0 while R2 >= r2min."""
    lo, hi = i0, i0
    while hi - lo + 1 < minpts:                 # minimum window
        if lo > 0 and valid[lo - 1]:
            lo -= 1
        if hi - lo + 1 < minpts and hi < len(x) - 1 and valid[hi + 1]:
            hi += 1
        if (lo == 0 or not valid[lo - 1]) and (hi == len(x) - 1 or not valid[hi + 1]):
            break
    while hi - lo + 1 < maxpts:
        cands = []
        if lo > 0 and valid[lo - 1]:
            cands.append((_r2(x[lo - 1:hi + 1], y[lo - 1:hi + 1]), lo - 1, hi))
        if hi < len(x) - 1 and valid[hi + 1]:
            cands.append((_r2(x[lo:hi + 2], y[lo:hi + 2]), lo, hi + 1))
        if not cands:
            break
        r2, nlo, nhi = max(cands)
        if r2 < r2min:
            break
        lo, hi = nlo, nhi
    return lo, hi


@dataclass
class LinFit:
    rows: tuple[int, int]      # rows (1 = first) in worksheet order, inclusive
    a: float
    b: float
    r2: float


def _fit_rows(x, y, lo, hi) -> LinFit:
    b, a = np.polyfit(x[lo:hi + 1], y[lo:hi + 1], 1)
    return LinFit((lo + 1, hi + 1), float(a), float(b), float(_r2(x[lo:hi + 1], y[lo:hi + 1])))


def tauc_window(lam, e, ty, a_corr, a_raw, lam_range, a_max=3.0, r2min=0.99) -> LinFit | None:
    """Linear region of the edge: starts at the edge center (max of -dA/dlambda) and grows while R2 >= r2min.

    lam is ascending (as in the worksheet), so E is descending.
    """
    lmin, lmax = sorted(lam_range)
    valid = (lam >= lmin) & (lam <= lmax) & (a_raw <= a_max) & np.isfinite(ty)
    if valid.sum() < 5:
        return None
    slope = -np.gradient(_smooth(a_corr), lam)
    slope[~valid] = -np.inf
    i0 = int(np.argmax(slope))
    lo, hi = _grow(e, ty, valid, i0, r2min, minpts=5, maxpts=200)
    f = _fit_rows(e, ty, lo, hi)
    return f if f.b > 0 else None


def urbach_window(e, alp, a_corr, eg, below=0.15, above=0.03, a_min=0.05,
                  slope_frac=0.7) -> LinFit | None:
    """Urbach tail: the steep, linear part of ln(alpha) vs E at the absorption edge.

    E_U = 1/slope of ln(alpha) at the edge (De Wolf 2014; Ledinsky 2019). The fit sits
    on the rising "shoulder" right before the gap, not on the slow rise below it
    (scattering/defects) nor on the plateau above it:
      1. point of maximum d(ln alpha)/dE within [Eg - below, Eg + above];
      2. the window grows while the local slope stays >= slope_frac of the maximum.
    Only points with corrected A >= a_min are used (near the baseline wavelength,
    A -> 0 by construction and ln(alpha) collapses).
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        la = np.where(alp > 0, np.log(alp), np.nan)
    valid = (e >= eg - below) & (e <= eg + above) & np.isfinite(la) & (a_corr >= a_min)
    if valid.sum() < 5:
        return None
    # smoothed derivative (E is descending; dividing by dE gives the right sign)
    sm = _smooth(np.where(np.isfinite(la), la, np.nanmin(la[valid])), 7)
    g = np.gradient(sm, e)
    g[~valid] = -np.inf
    i0 = int(np.argmax(g))
    gmax = g[i0]
    if not np.isfinite(gmax) or gmax <= 0:
        return None
    steep = valid & (g >= slope_frac * gmax)
    lo = hi = i0
    while lo > 0 and steep[lo - 1]:
        lo -= 1
    while hi < len(e) - 1 and steep[hi + 1]:
        hi += 1
    if hi - lo + 1 < 5:                          # guarantees a minimum number of points
        lo, hi = max(0, i0 - 2), min(len(e) - 1, i0 + 2)
    f = _fit_rows(e, la, lo, hi)
    return f if f.b > 0 else None


def suggest_range(lam, a_corr, a_raw=None, a_max=3.0, width=45.0, lam_min=300.0) -> tuple[float, float]:
    """Absorption edge with the longest wavelength (the perovskite, not residual PbI2).

    Below lam_min (deep UV) glass/ITO absorbs and the signal is noisy: excluded from the search.
    """
    d = -np.gradient(_smooth(a_corr, 9), lam)
    d[lam < lam_min] = 0
    if a_raw is not None:                       # ignore the saturated region and its neighborhood
        bad = np.convolve((a_raw > a_max).astype(float), np.ones(9), mode="same") > 0
        d[bad] = 0
    d[~np.isfinite(d)] = 0
    if d.max() <= 0:
        return float(lam.min()), float(lam.max())
    # local peaks with at least 30 % of the largest one
    peaks = [i for i in range(2, len(d) - 2)
             if d[i] >= d[i - 1] and d[i] >= d[i + 1] and d[i] >= 0.3 * d.max()]
    i = max(peaks, key=lambda k: lam[k]) if peaks else int(np.argmax(d))
    return float(lam[i] - width), float(lam[i] + width)


# ------------------------------------------------------------ per-sample result
@dataclass
class TaucResult:
    e: np.ndarray
    alpha: np.ndarray
    ty: np.ndarray
    ln_alpha: np.ndarray
    tauc: LinFit | None
    urbach: LinFit | None

    @property
    def eg(self):
        return -self.tauc.a / self.tauc.b if self.tauc else None

    @property
    def eu_mev(self):
        return 1000.0 / self.urbach.b if self.urbach else None

    @property
    def urbach_ok(self):
        """A real exponential tail: E_U up to ~100 meV and very linear."""
        return bool(self.urbach and self.eu_mev <= URBACH_MAX_MEV and self.urbach.r2 >= 0.99)


URBACH_MAX_MEV = 100.0


def tauc_analysis(lam, a_raw, a_corr, n, d_nm, lam_range, a_max=3.0) -> TaucResult:
    e = HC / lam
    alp = alpha(a_corr, d_nm)
    alp = np.where(a_raw > a_max, np.nan, alp)          # saturated: excluded
    ty = tauc_y(e, alp, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        la = np.where(alp > 0, np.log(alp), np.nan)
    tf = tauc_window(lam, e, ty, a_corr, a_raw, lam_range, a_max)
    uf = urbach_window(e, alp, a_corr, -tf.a / tf.b) if tf else None
    return TaucResult(e, alp, ty, la, tf, uf)
