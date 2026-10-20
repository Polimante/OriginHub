"""The data contract every reader must meet (core.dataset.validate)."""
from pathlib import Path

import numpy as np
import pytest

from core.dataset import DataError, Dataset, read_text, validate, x_signature


def _ds(x, y, name="s"):
    return Dataset("ABS", name, np.asarray(x, float), np.asarray(y, float), Path("f.txt"))


def test_accepts_isolated_nan():
    validate(_ds([1, 2, 3], [0.1, np.nan, 0.3]))


@pytest.mark.parametrize("x, y, reason", [
    ([1, 2, 3], [1, 2], "x values but"),
    ([1], [1], "fewer than 2"),
    ([1, np.nan, 3], [1, 2, 3], "NaN or infinite"),
    ([1, 3, 2], [1, 2, 3], "not strictly ascending"),
    ([1, 2, 2], [1, 2, 3], "not strictly ascending"),
    ([1, 2, 3], [1, np.inf, 3], "infinite"),
    ([1, 2, 3], [np.nan] * 3, "no numeric"),
])
def test_rejects(x, y, reason):
    with pytest.raises(DataError, match=reason):
        validate(_ds(x, y))


def test_rejects_empty_name():
    with pytest.raises(DataError, match="empty sample name"):
        validate(_ds([1, 2], [1, 2], name="  "))


def test_x_signature_distinguishes_grids():
    a = _ds(np.arange(400.0, 851.0), np.zeros(451))
    b = _ds(np.arange(400.0, 851.0), np.ones(451))
    c = _ds(np.arange(400.0, 850.5, 0.5), np.zeros(901))
    assert x_signature(a) == x_signature(b) != x_signature(c)


@pytest.mark.parametrize("encoding", ["utf-8", "cp1252"])
def test_read_text_any_encoding(tmp_path, encoding):
    f = tmp_path / "t.txt"
    f.write_bytes("Amostra açúcar 25 °C".encode(encoding))
    assert read_text(f) == "Amostra açúcar 25 °C"
