"""Static checks of the code that runs INSIDE Origin.

CI cannot run Origin (it needs a license), so these catch what would otherwise only
fail on the user's machine: syntax errors and imports that Origin's embedded Python lacks.
The full check is tools/e2e_test.py, run on a machine with Origin before each release.
"""
import ast
import sys
from pathlib import Path

import pytest

from core.origin_bridge import ORIGIN_COMMON
from core.registry import discover

SCRIPTS = [ORIGIN_COMMON] + [t.origin_script for t in discover().techniques.values()]
# Origin's embedded Python 3.11 has the standard library and originpro - no numpy/pandas.
# origin_build may import origin_common (copied next to it in the run folder).
ALLOWED = set(sys.stdlib_module_names) | {"originpro", "PyOrigin", "origin_common", "origin_build"}


def _ids(p: Path):
    return f"{p.parent.name}/{p.name}"


@pytest.mark.parametrize("path", SCRIPTS, ids=_ids)
def test_compiles_as_python_311(path):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 11))


@pytest.mark.parametrize("path", SCRIPTS, ids=_ids)
def test_imports_only_what_origin_has(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            used |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise AssertionError("relative imports do not work inside Origin (the file is copied alone)")
            used.add(node.module.split(".")[0])
    assert not used - ALLOWED, f"not available inside Origin: {sorted(used - ALLOWED)}"


@pytest.mark.parametrize("path", SCRIPTS[1:], ids=_ids)
def test_names_imported_from_common_exist(path):
    common = {n.name for n in ast.parse(ORIGIN_COMMON.read_text(encoding="utf-8")).body
              if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    common |= {t.id for n in ast.parse(ORIGIN_COMMON.read_text(encoding="utf-8")).body
               if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module == "origin_common":
            missing = {a.name for a in node.names} - common
            assert not missing, f"not defined in origin_common.py: {sorted(missing)}"


def test_common_runner_reports_ok():
    src = ORIGIN_COMMON.read_text(encoding="utf-8")
    assert 'log("OK")' in src, "the app waits for the final OK line in the log"
    assert "origin_build.build(cfg)" in src
