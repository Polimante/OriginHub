"""UV-Vis readers and content-based recognition, on synthetic files in the real formats."""
import numpy as np
import pytest

from core.dataset import validate
from techniques.uvvis import TECHNIQUE
from techniques.uvvis import readers as rd


def test_detect_by_content(jasco_file, agilent_file, tmp_path):
    assert rd.detect_jasco(jasco_file) == 1.0
    assert rd.detect_agilent_sd(agilent_file) == 1.0
    assert rd.detect_jasco(agilent_file) == 0.0
    assert rd.detect_agilent_sd(jasco_file) == 0.0
    other = tmp_path / "notes.txt"
    other.write_text("just some text\n1 2\n3 4\n")
    assert rd.detect_jasco(other) == 0.0


def test_detect_ignores_the_file_name(jasco_file, tmp_path):
    renamed = tmp_path / "renamed.dat"
    renamed.write_bytes(jasco_file.read_bytes())
    assert rd.detect_jasco(renamed) == 1.0


def test_jasco(jasco_file):
    (ds,) = rd.read_jasco(jasco_file)
    validate(ds)
    assert ds.kind == TECHNIQUE.key
    assert ds.name == "film_A"                      # the file name wins over the internal title
    assert ds.meta["sample_name"] == "film A internal"
    assert len(ds.x) == 901
    assert ds.x[0] == 400.0 and ds.x[-1] == 850.0   # sorted ascending


def test_jasco_decimal_comma(tmp_path):
    f = tmp_path / "comma.txt"           # Portuguese/Spanish Windows locales write "0,1"
    f.write_text("TITLE\tx\nDATA TYPE\tULTRAVIOLET SPECTRUM\nXYDATA\n"
                 "802,0\t0,1\n801,0\t0,2\n800,0\t0,3\n\nSample name\tx\n", encoding="cp1252")
    (ds,) = rd.read_jasco(f)
    assert ds.x.tolist() == [800.0, 801.0, 802.0]
    assert ds.y.tolist() == [0.3, 0.2, 0.1]


def test_agilent_multi_spectrum(agilent_file):
    out = rd.read_agilent_sd(agilent_file)
    assert [d.name for d in out] == ["FAPI_1", "FAPI_2", "FAPI_1_2"]   # repeated name gets a suffix
    for d in out:
        validate(d)
        assert d.x[0] == 190.0 and d.x[-1] == 1100.0 and len(d.x) == 911
        assert d.meta["instrument"] == "SYNTH"
    assert not np.allclose(out[0].y, out[1].y)


def test_agilent_without_spectra(tmp_path):
    f = tmp_path / "empty.SD"
    f.write_bytes(b"\x0232\x00\rREGISTER FILE\x00CHPUVObject" + b"\x00" * 64)
    with pytest.raises(ValueError):
        rd.read_agilent_sd(f)
