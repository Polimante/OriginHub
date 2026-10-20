"""Smoke test of the window, without a display (QT_QPA_PLATFORM=offscreen, set in conftest)."""
import pytest

pytest.importorskip("PyQt6")
pytestmark = pytest.mark.gui

from PyQt6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402
from parsers import ABS, XRD  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    w = main.MainWindow()
    yield w
    w.close()


def test_window_opens_with_one_tab_per_technique(window):
    assert set(window.kind_tabs) == {ABS, XRD}
    assert window.tabs.count() == 2


def test_loading_files_fills_the_right_tabs(window, jasco_file, agilent_file, powdll_file, tmp_path):
    junk = tmp_path / "junk.txt"
    junk.write_text("not a spectrum")
    window.load_paths([jasco_file, agilent_file, powdll_file, junk])
    assert len(window.kind_tabs[ABS].datasets) == 4          # 1 JASCO + 3 Agilent spectra
    assert len(window.kind_tabs[XRD].datasets) == 2
    assert window.kind_tabs[ABS].table.rowCount() == 4
    assert "Skipped: 1" in window.statusBar().currentMessage()


def test_loading_a_folder(window, jasco_file):
    window.load_paths([jasco_file.parent])
    assert len(window.kind_tabs[ABS].datasets) == 1


def test_help_file_exists():
    assert main.HELP_FILE.is_file()
