import os
import sys
from pathlib import Path

import numpy as np
import pytest

# GUI tests must not open a window (CI machines have no display)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synthetic  # noqa: E402

LAM = np.arange(400.0, 1100.5, 1.0)          # nm, ascending
TWO_THETA = np.round(np.arange(5.0, 60.0, 0.02), 4)


@pytest.fixture
def jasco_file(tmp_path):
    lam_desc = np.arange(850.0, 399.9, -0.5)    # the V-780 writes from long to short wavelength
    return synthetic.write_jasco(tmp_path / "film_A.txt", lam_desc, synthetic.uvvis_absorbance(lam_desc),
                                 title="internal title", sample_name="film A internal")


@pytest.fixture
def agilent_file(tmp_path):
    spectra = [("FAPI_1", 190.0, 1.0, synthetic.uvvis_absorbance(np.arange(190.0, 1100.5, 1.0))),
               ("FAPI_2", 190.0, 1.0, synthetic.uvvis_absorbance(np.arange(190.0, 1100.5, 1.0), eg=1.60)),
               ("FAPI_1", 190.0, 1.0, synthetic.uvvis_absorbance(np.arange(190.0, 1100.5, 1.0)))]
    return synthetic.write_agilent_sd(tmp_path / "run.SD", spectra)


@pytest.fixture
def powdll_file(tmp_path):
    return synthetic.write_powdll(tmp_path / "xrd.xlsx", TWO_THETA,
                                  {"film A": synthetic.xrd_pattern(TWO_THETA),
                                   "film B": synthetic.xrd_pattern(TWO_THETA, background=80.0)})
