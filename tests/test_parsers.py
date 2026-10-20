"""Readers and content-based recognition, on synthetic files in the real formats."""
from pathlib import Path

import numpy as np
import pytest
from conftest import TWO_THETA

import parsers
from parsers import ABS, UNKNOWN, XRD, DataError, Dataset


def test_detect_by_content(jasco_file, agilent_file, powdll_file, tmp_path):
    assert parsers.detect(jasco_file) == ABS
    assert parsers.detect(agilent_file) == ABS
    assert parsers.detect(powdll_file) == XRD
    other = tmp_path / "notes.txt"
    other.write_text("just some text\n1 2\n3 4\n")
    assert parsers.detect(other) == UNKNOWN


def test_detect_ignores_the_file_name(jasco_file, tmp_path):
    renamed = tmp_path / "renamed.dat"
    renamed.write_bytes(jasco_file.read_bytes())
    assert parsers.detect(renamed) == ABS


def test_unknown_file_raises(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hello")
    with pytest.raises(ValueError, match="Unrecognized"):
        parsers.load(f)


def test_jasco(jasco_file):
    (ds,) = parsers.load(jasco_file)
    assert ds.kind == ABS
    assert ds.name == "film_A"                      # the file name wins over the internal title
    assert ds.meta["sample_name"] == "film A internal"
    assert len(ds.x) == 901
    assert ds.x[0] == 400.0 and ds.x[-1] == 850.0   # sorted ascending
    assert np.all(np.diff(ds.x) > 0)


def test_jasco_decimal_comma(tmp_path):
    f = tmp_path / "comma.txt"           # Portuguese/Spanish Windows locales write "0,1"
    f.write_text("TITLE\tx\nDATA TYPE\tULTRAVIOLET SPECTRUM\nXYDATA\n"
                 "802,0\t0,1\n801,0\t0,2\n800,0\t0,3\n\nSample name\tx\n", encoding="cp1252")
    (ds,) = parsers.load(f)
    assert ds.x.tolist() == [800.0, 801.0, 802.0]
    assert ds.y.tolist() == [0.3, 0.2, 0.1]


def test_agilent_multi_spectrum(agilent_file):
    out = parsers.load(agilent_file)
    assert [d.name for d in out] == ["FAPI_1", "FAPI_2", "FAPI_1_2"]   # repeated name gets a suffix
    for d in out:
        assert d.kind == ABS
        assert d.x[0] == 190.0 and d.x[-1] == 1100.0 and len(d.x) == 911
        assert d.meta["instrument"] == "SYNTH"
    assert not np.allclose(out[0].y, out[1].y)


def test_agilent_without_spectra(tmp_path):
    f = tmp_path / "empty.SD"
    f.write_bytes(b"\x0232\x00\rREGISTER FILE\x00CHPUVObject" + b"\x00" * 64)
    with pytest.raises(ValueError):
        parsers.load(f)


def test_powdll(powdll_file):
    out = parsers.load(powdll_file)
    assert [d.name for d in out] == ["film A", "film B"]
    for d in out:
        assert d.kind == XRD
        np.testing.assert_allclose(d.x, TWO_THETA)
    assert out[0].x[np.argmax(out[0].y)] == pytest.approx(13.9, abs=0.02)


def test_x_signature_groups_equal_axes(agilent_file, jasco_file):
    a1, a2, _ = parsers.load(agilent_file)
    (j,) = parsers.load(jasco_file)
    assert parsers.x_signature(a1) == parsers.x_signature(a2)
    assert parsers.x_signature(a1) != parsers.x_signature(j)


# ------------------------------------------------------------- validation
def _ds(x, y, name="s"):
    return Dataset(ABS, name, np.asarray(x, float), np.asarray(y, float), Path("f.txt"))


def test_validate_accepts_isolated_nan():
    parsers.validate(_ds([1, 2, 3], [0.1, np.nan, 0.3]))


@pytest.mark.parametrize("x, y, reason", [
    ([1, 2, 3], [1, 2], "x values but"),
    ([1], [1], "fewer than 2"),
    ([1, np.nan, 3], [1, 2, 3], "NaN or infinite"),
    ([1, 3, 2], [1, 2, 3], "not strictly ascending"),
    ([1, 2, 2], [1, 2, 3], "not strictly ascending"),
    ([1, 2, 3], [1, np.inf, 3], "infinite"),
    ([1, 2, 3], [np.nan] * 3, "no numeric"),
])
def test_validate_rejects(x, y, reason):
    with pytest.raises(DataError, match=reason):
        parsers.validate(_ds(x, y))


def test_validate_rejects_empty_name():
    with pytest.raises(DataError, match="empty sample name"):
        parsers.validate(_ds([1, 2], [1, 2], name="  "))
