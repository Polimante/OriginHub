"""Synthetic XRD files in the real formats (registered in the root conftest.py)."""
import numpy as np
import pytest

from . import synthetic

TWO_THETA = np.round(np.arange(5.0, 60.0, 0.02), 4)


@pytest.fixture
def powdll_file(tmp_path):
    return synthetic.write_powdll(tmp_path / "xrd.xlsx", TWO_THETA,
                                  {"film A": synthetic.xrd_pattern(TWO_THETA),
                                   "film B": synthetic.xrd_pattern(TWO_THETA, background=80.0)})
