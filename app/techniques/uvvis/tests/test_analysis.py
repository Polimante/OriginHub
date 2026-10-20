"""Scientific checks: the analysis must recover the band gap and Urbach energy of
synthetic spectra whose true values are known, and must not drift silently.
"""
import numpy as np
import pytest

from techniques.uvvis import analysis as an
from techniques.uvvis.tests.fixtures import LAM
from techniques.uvvis.tests.synthetic import HC, uvvis_absorbance


def run(eg=1.55, eu=0.020, d_nm=400.0, noise=0.0, ref=1000.0, n=0.5):
    a = uvvis_absorbance(LAM, eg, eu, d_nm=d_nm, noise=noise)
    a_corr, _ = an.baseline(LAM, a, ref)
    rng = an.suggest_range(LAM, a_corr, a)
    return an.tauc_analysis(LAM, a, a_corr, n, d_nm, rng), rng


# ------------------------------------------------------------ building blocks
def test_baseline_subtracts_mean_around_ref():
    x = np.arange(800.0, 901.0)
    y = np.full_like(x, 0.5)
    y[(x >= 848) & (x <= 852)] = [0.4, 0.5, 0.6, 0.5, 0.4]
    corr, v = an.baseline(x, y, 850.0)
    assert v == pytest.approx(0.48)
    np.testing.assert_allclose(corr, y - 0.48)


def test_baseline_outside_the_axis_uses_nearest_point():
    x = np.arange(400.0, 851.0)
    _, v = an.baseline(x, x / 1000, 1000.0)
    assert v == pytest.approx(0.850)


def test_transmittance():
    np.testing.assert_allclose(an.transmittance(np.array([0.0, 1.0, 2.0])), [100.0, 10.0, 1.0])


def test_alpha_units():
    assert an.alpha(np.array([1.0]), 400.0)[0] == pytest.approx(2.303 / 400e-7)
    assert an.alpha(np.array([1.0]), None)[0] == pytest.approx(2.303)


@pytest.mark.parametrize("label, n", list(an.TRANSITIONS.items()))
def test_every_transition_has_an_exponent_label(label, n):
    assert n in an.EXPONENT_LABEL


def test_material_transition_ids_map_to_labels():
    assert set(an.TRANSITION_IDS.values()) == set(an.TRANSITIONS)


def test_edge_search_follows_material_settings():
    """A wide-gap material: the edge must be found inside the search region of its profile."""
    a = uvvis_absorbance(LAM, eg=2.30, eu=0.025)
    a_corr, _ = an.baseline(LAM, a, 700.0)
    lo, hi = an.suggest_range(LAM, a_corr, a, width=35.0, lam_min=400.0)
    assert hi - lo == pytest.approx(70.0)
    assert lo < HC / 2.30 < hi


# ------------------------------------------------------------ known answers
@pytest.mark.parametrize("eg, eu", [(1.55, 0.020), (1.60, 0.015), (2.30, 0.025), (1.55, 0.040)])
def test_recovers_known_band_gap_and_urbach_energy(eg, eu):
    r, rng = run(eg, eu)
    # the edge search must land on the absorption edge
    assert rng[0] < HC / eg < rng[1]
    # the Urbach tail rounds the edge, so the Tauc extrapolation lands slightly below Eg
    assert r.eg == pytest.approx(eg, abs=0.015)
    assert r.eu_mev == pytest.approx(eu * 1000, rel=0.10)
    assert r.tauc.r2 >= 0.99
    assert r.urbach_ok


def test_band_gap_does_not_depend_on_thickness():
    a = uvvis_absorbance(LAM)
    a_corr, _ = an.baseline(LAM, a, 1000.0)
    rng = an.suggest_range(LAM, a_corr, a)
    with_d = an.tauc_analysis(LAM, a, a_corr, 0.5, 400.0, rng)
    without_d = an.tauc_analysis(LAM, a, a_corr, 0.5, None, rng)
    assert without_d.eg == pytest.approx(with_d.eg, abs=1e-9)
    assert without_d.eu_mev == pytest.approx(with_d.eu_mev, abs=1e-6)


def test_robust_to_measurement_noise():
    clean = run()[0]
    noisy = run(noise=1e-3)[0]
    assert noisy.eg == pytest.approx(clean.eg, abs=0.005)
    assert noisy.eu_mev == pytest.approx(clean.eu_mev, rel=0.10)


def test_saturated_points_are_excluded():
    a = uvvis_absorbance(LAM, d_nm=4000.0)          # thick film: A > 3 above the gap
    a_corr, _ = an.baseline(LAM, a, 1000.0)
    rng = an.suggest_range(LAM, a_corr, a)
    r = an.tauc_analysis(LAM, a, a_corr, 0.5, 4000.0, rng)
    assert np.all(np.isnan(r.alpha[a > 3.0]))
    lo, hi = r.tauc.rows
    assert np.all(a[lo - 1:hi] <= 3.0)


def test_flat_spectrum_gives_no_fit():
    a = np.full_like(LAM, 0.2)
    a_corr, _ = an.baseline(LAM, a, 1000.0)
    r = an.tauc_analysis(LAM, a, a_corr, 0.5, None, an.suggest_range(LAM, a_corr, a))
    assert r.tauc is None and r.eg is None and r.urbach is None


# ------------------------------------------------------------ regression lock
def test_reference_spectrum_is_unchanged():
    """Locks the exact output for the reference synthetic film (Eg = 1.55 eV, E_U = 20 meV).

    If this fails, the fit-window algorithm changed. That can be fine, but it must be a
    deliberate scientific decision: explain it in the pull request and update these numbers.
    """
    r, rng = run()
    assert rng == (749.0, 839.0)
    assert r.tauc.rows == (350, 409)
    assert r.eg == pytest.approx(1.54534, abs=5e-5)
    assert r.eu_mev == pytest.approx(20.303, abs=5e-3)
