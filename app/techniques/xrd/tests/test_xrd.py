"""XRD reader and payload, on synthetic PowDLL files."""
import json

import numpy as np
import pytest

from core import origin_bridge as ob
from core.dataset import validate
from techniques.xrd import TECHNIQUE
from techniques.xrd import readers as rd
from techniques.xrd.tests.fixtures import TWO_THETA


def test_detect(powdll_file, tmp_path):
    assert rd.detect_powdll(powdll_file) == 1.0
    other = tmp_path / "table.xlsx"
    import pandas as pd
    pd.DataFrame([["a", "b"], [1, 2]]).to_excel(other, header=False, index=False)
    assert rd.detect_powdll(other) == 0.0
    broken = tmp_path / "broken.xls"
    broken.write_bytes(b"not an excel file")
    assert rd.detect_powdll(broken) == 0.0


def test_powdll(powdll_file):
    out = rd.read_powdll(powdll_file)
    assert [d.name for d in out] == ["film A", "film B"]
    for d in out:
        validate(d)
        assert d.kind == TECHNIQUE.key
        np.testing.assert_allclose(d.x, TWO_THETA)
    assert out[0].x[np.argmax(out[0].y)] == pytest.approx(13.9, abs=0.02)


def test_payload(powdll_file):
    p = json.loads(json.dumps(ob.build_payload(TECHNIQUE, rd.read_powdll(powdll_file), None)))
    (g,) = p["groups"]
    for s in g["series"]:
        assert min(s["y_norm"]) == 0.0 and max(s["y_norm"]) == 1.0
        assert len(s["y"]) == len(g["x"])


def test_different_axes_are_refused(powdll_file):
    a, b = rd.read_powdll(powdll_file)
    b.x, b.y = b.x[:-10], b.y[:-10]
    with pytest.raises(ValueError, match="different 2theta"):
        ob.build_payload(TECHNIQUE, [a, b], None)
