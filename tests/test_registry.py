"""Plugin discovery and isolation: a broken technique must never take the others down."""
import textwrap
from pathlib import Path

import numpy as np
import pytest

from core.dataset import DataError, Dataset
from core.registry import Reader, Registry, Technique, check_technique, discover

GOOD = '''
from pathlib import Path
import numpy as np
from core.dataset import Dataset
from core.registry import Reader, Technique

def detect(path):
    return 1.0 if path.suffix == ".good" else 0.0

def read(path):
    return [Dataset("", path.stem, np.array([1.0, 2.0]), np.array([3.0, 4.0]), path)]

class Good(Technique):
    key = "GOOD"
    title = "Good"
    readers = [Reader("good format", detect, read)]
    origin_script = Path(__file__).with_name("origin_build.py")

TECHNIQUE = Good()
'''


def make_plugins(root: Path) -> str:
    pkg = root / "fakeplugins"
    plugins = {
        "good": GOOD,
        "broken_import": "import this_module_does_not_exist\n",
        "no_readers": GOOD.replace('readers = [Reader("good format", detect, read)]', "readers = []"),
        "same_key": GOOD,                                   # duplicate of "good"
    }
    for name, code in plugins.items():
        (pkg / name).mkdir(parents=True)
        (pkg / name / "__init__.py").write_text(textwrap.dedent(code))
        (pkg / name / "origin_build.py").write_text("def build(cfg):\n    pass\n")
    (pkg / "_ignored").mkdir()
    (pkg / "_ignored" / "__init__.py").write_text("raise RuntimeError('must not be imported')\n")
    (pkg / "__init__.py").write_text("")
    return "fakeplugins"


def test_broken_plugins_are_isolated(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    reg = discover(make_plugins(tmp_path))
    assert list(reg.techniques) == ["GOOD"]
    assert set(reg.failures) == {"broken_import", "no_readers", "same_key"}
    assert "this_module_does_not_exist" in reg.failures["broken_import"]
    assert "at least one Reader" in reg.failures["no_readers"]
    assert "already used" in reg.failures["same_key"]


def test_real_techniques_load_without_failures():
    reg = discover()
    assert not reg.failures, reg.failures
    assert {"ABS", "XRD"} <= set(reg.techniques)
    for t in reg.techniques.values():
        check_technique(t)


# ------------------------------------------------------------ routing
def _tech(key, readers):
    t = Technique()
    t.key, t.title, t.readers = key, key, readers
    return t


def _ds(path, x=(1.0, 2.0)):
    return [Dataset("", "s", np.array(x), np.array([1.0, 2.0]), path)]


def test_identify_picks_the_most_confident_reader(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    weak = Reader("weak", lambda p: 0.4, _ds)
    strong = Reader("strong", lambda p: 0.9, _ds)
    reg = Registry({"A": _tech("A", [weak]), "B": _tech("B", [strong])})
    t, r = reg.identify(f)
    assert (t.key, r.name) == ("B", "strong")


def test_a_crashing_detector_counts_as_no_match(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")

    def boom(path):
        raise RuntimeError("bug in a plugin")

    reg = Registry({"A": _tech("A", [Reader("bad", boom, _ds)]),
                    "B": _tech("B", [Reader("ok", lambda p: 0.5, _ds)])})
    assert reg.identify(f)[0].key == "B"


def test_load_sets_kind_and_validates(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    reg = Registry({"A": _tech("A", [Reader("ok", lambda p: 1.0, _ds)])})
    t, out = reg.load(f)
    assert out[0].kind == "A"
    bad = Registry({"A": _tech("A", [Reader("unsorted", lambda p: 1.0, lambda p: _ds(p, x=(2.0, 1.0)))])})
    with pytest.raises(DataError, match="ascending"):
        bad.load(f)


def test_unknown_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(ValueError, match="Unrecognized"):
        Registry().load(f)


@pytest.mark.parametrize("key", ["", "abs", "A", "WAY_TOO_LONG_KEY_NAME", "A-B"])
def test_invalid_keys_are_rejected(key, tmp_path):
    script = tmp_path / "origin_build.py"
    script.write_text("def build(cfg):\n    pass\n")
    t = _tech(key, [Reader("r", lambda p: 1.0, _ds)])
    t.origin_script = script
    with pytest.raises(ValueError, match="invalid key"):
        check_technique(t)


def test_origin_script_must_define_build(tmp_path):
    script = tmp_path / "origin_build.py"
    script.write_text("def make(cfg):\n    pass\n")
    t = _tech("OK", [Reader("r", lambda p: 1.0, _ds)])
    t.origin_script = script
    with pytest.raises(ValueError, match="must define build"):
        check_technique(t)
