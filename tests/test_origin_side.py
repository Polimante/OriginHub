"""Static checks of the code that runs INSIDE Origin.

CI cannot run Origin (it needs a license), so these catch what would otherwise only
fail on the user's machine: syntax errors and imports that Origin's embedded Python lacks.
The full check is tools/e2e_test.py, run on a machine with Origin before each release.
"""
import ast
import sys
from pathlib import Path

import pytest

ORIGIN_SIDE = sorted((Path(__file__).resolve().parent.parent / "app" / "origin_side").glob("*.py"))
# Origin's embedded Python 3.11 has the standard library and originpro - no numpy/pandas
ALLOWED = set(sys.stdlib_module_names) | {"originpro", "PyOrigin"}


@pytest.mark.parametrize("path", ORIGIN_SIDE, ids=lambda p: p.name)
def test_compiles_as_python_311(path):
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path), feature_version=(3, 11))


@pytest.mark.parametrize("path", ORIGIN_SIDE, ids=lambda p: p.name)
def test_imports_only_what_origin_has(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            used |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            used.add(node.module.split(".")[0])
    assert not used - ALLOWED, f"not available inside Origin: {sorted(used - ALLOWED)}"


def test_build_script_expects_injected_payload():
    src = (Path(__file__).resolve().parent.parent / "app" / "origin_side" / "build.py").read_text(encoding="utf-8")
    assert "PAYLOAD = " not in src, "PAYLOAD is prepended by origin_bridge.launch(), not defined in build.py"
    assert 'log("OK")' in src, "the app waits for the final OK line in the log"
