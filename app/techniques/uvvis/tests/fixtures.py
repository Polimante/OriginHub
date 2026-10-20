"""Synthetic UV-Vis files in the real formats (registered in the root conftest.py)."""
import numpy as np
import pytest

from . import synthetic

LAM = np.arange(400.0, 1100.5, 1.0)          # nm, ascending


@pytest.fixture
def jasco_file(tmp_path):
    lam_desc = np.arange(850.0, 399.9, -0.5)    # the V-780 writes from long to short wavelength
    return synthetic.write_jasco(tmp_path / "film_A.txt", lam_desc, synthetic.uvvis_absorbance(lam_desc),
                                 title="internal title", sample_name="film A internal")


@pytest.fixture
def agilent_file(tmp_path):
    lam = np.arange(190.0, 1100.5, 1.0)
    spectra = [("FAPI_1", 190.0, 1.0, synthetic.uvvis_absorbance(lam)),
               ("FAPI_2", 190.0, 1.0, synthetic.uvvis_absorbance(lam, eg=1.60)),
               ("FAPI_1", 190.0, 1.0, synthetic.uvvis_absorbance(lam))]
    return synthetic.write_agilent_sd(tmp_path / "run.SD", spectra)
