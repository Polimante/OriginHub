"""Release bookkeeping: version number, changelog section, and the --check self-test."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from version import __version__

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import release_notes  # noqa: E402


def test_version_is_semantic():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_current_version_has_release_notes():
    notes = release_notes.section(__version__, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert notes.strip()


def test_release_notes_extracts_only_one_section():
    text = "# Changelog\n\n## [Unreleased]\n\n## [1.1.0] - x\n### Added\n- b\n\n## [1.0.0] - y\n- a\n"
    assert release_notes.section("1.1.0", text) == "### Added\n- b\n"
    assert release_notes.section("1.0.0", text) == "- a\n"
    with pytest.raises(SystemExit):
        release_notes.section("2.0.0", text)
    with pytest.raises(SystemExit):
        release_notes.section("Unreleased", text)   # empty section


def test_installer_bundles_every_origin_script():
    """The PyInstaller spec must ship each technique's origin_build.py (copied to Origin at run time)."""
    spec = (ROOT / "packaging" / "OriginHub.spec").read_text(encoding="utf-8")
    assert 'glob("*/origin_build.py")' in spec
    assert '"origin_side" / "origin_common.py"' in spec
    assert 'glob("*.toml")' in spec


def test_self_check_passes(tmp_path):
    import main
    report = tmp_path / "check.txt"
    assert main.check(report) == 0
    text = report.read_text(encoding="utf-8")
    assert __version__ in text and text.strip().endswith("OK")


def test_release_notes_script_writes_utf8_on_any_console():
    """The CHANGELOG has non-ASCII text (→, ₂); CI's Windows console uses cp1252."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env["PYTHONIOENCODING"] = "cp1252"
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "release_notes.py"), __version__],
                         capture_output=True, env=env)
    assert out.returncode == 0, out.stderr.decode(errors="replace")
    assert out.stdout.decode("utf-8").strip()
