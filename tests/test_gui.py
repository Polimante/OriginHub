"""Smoke test of the window, without a display (QT_QPA_PLATFORM=offscreen, set in conftest)."""
import pytest

pytest.importorskip("PyQt6")
pytestmark = pytest.mark.gui

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402
from core.registry import Registry, discover  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path):
    """Never touch the user's real settings (Windows registry)."""
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def window(app, settings):
    w = main.MainWindow(settings=settings)
    yield w
    w.close()


def test_window_opens_with_one_tab_per_technique(window):
    assert {"ABS", "XRD"} <= set(window.kind_tabs)
    assert window.tabs.count() == len(window.registry.techniques)


def test_loading_files_fills_the_right_tabs(window, jasco_file, agilent_file, powdll_file, tmp_path):
    junk = tmp_path / "junk.txt"
    junk.write_text("not a spectrum")
    window.load_paths([jasco_file, agilent_file, powdll_file, junk])
    assert len(window.kind_tabs["ABS"].datasets) == 4          # 1 JASCO + 3 Agilent spectra
    assert len(window.kind_tabs["XRD"].datasets) == 2
    assert window.kind_tabs["ABS"].table.rowCount() == 4
    assert "Skipped: 1" in window.statusBar().currentMessage()


def test_loading_a_folder(window, jasco_file):
    window.load_paths([jasco_file.parent])
    assert len(window.kind_tabs["ABS"].datasets) == 1


def test_uvvis_preview_shows_the_band_gap(window, agilent_file):
    window.load_paths([agilent_file])
    tab = window.kind_tabs["ABS"]
    eg = tab.table.item(0, 7).text()                       # Eg column
    assert 1.50 < float(eg) < 1.56


def test_material_profile_sets_the_uvvis_defaults(window, agilent_file):
    window.load_paths([agilent_file])
    tab = window.kind_tabs["ABS"]
    names = [m.name for m in window.materials]
    window.material_box.setCurrentIndex(names.index("FAPbI3"))
    assert tab.ref.value() == 1000.0
    assert tab.options()["ref_nm"] == 1000.0
    window.material_box.setCurrentIndex(names.index("CsPbBr3"))
    assert tab.ref.value() == 700.0
    assert tab.options()["edge_window_nm"] == 35.0


def test_a_broken_technique_does_not_block_the_others(app, jasco_file):
    good = discover()
    reg = Registry(dict(good.techniques), {"fancy_new_technique": "Traceback: SyntaxError in fancy plugin"})
    abs_tech = reg.techniques["ABS"]

    class Broken(type(abs_tech)):
        title = "Broken tab"

        def make_tab(self, main):
            raise RuntimeError("bug while building the tab")

    reg.techniques["XRD"] = Broken()
    w = main.MainWindow(reg, settings=QSettings(str(jasco_file.parent / "s.ini"), QSettings.Format.IniFormat))
    titles = [w.tabs.tabText(i) for i in range(w.tabs.count())]
    assert "⚠ Broken tab" in titles and "⚠ fancy_new_technique" in titles
    assert set(w.kind_tabs) == {"ABS"}
    w.load_paths([jasco_file])
    assert len(w.kind_tabs["ABS"].datasets) == 1
    w.close()


def test_help_file_exists():
    assert main.HELP_FILE.is_file()


def test_help_menu_has_updates_and_setup(window):
    btn = next(b for b in window.findChildren(main.QPushButton) if b.text() == "Help")
    assert [a.text() for a in btn.menu().actions()] == ["User guide…", "Check for updates…", "Setup check…",
                                                        "About OriginHub…"]


def test_startup_is_quiet_after_the_first_run(window, settings, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "setup_check", lambda: calls.append("setup"))
    monkeypatch.setattr(window, "check_updates", lambda manual: calls.append(("updates", manual)))
    window.startup()                                   # first run: setup check, then background update check
    assert calls == ["setup", ("updates", False)]
    calls.clear()
    settings.setValue("updates/auto", False)
    window.startup()                                   # later runs: nothing unless updates are on
    assert calls == []


def test_setup_dialog_lists_the_checks(app, settings, tmp_path):
    from core.dialogs import SetupDialog
    d = SetupDialog(settings, work=tmp_path)
    titles = [d.table.item(i, 0).text() for i in range(d.table.rowCount())]
    assert titles == ["Origin", "Work folder", "Graph template"]
    d.close()


def test_update_dialog_skip_remembers_the_version(app, settings):
    from core.dialogs import UpdateDialog
    from core.updater import Release
    rel = Release("99.0.0", "* new things", "https://x", "https://x/a.exe", "a.exe", "https://x/a.sha256", 1)
    d = UpdateDialog(rel, settings)
    assert d.btn_go.text() == "Open download page"     # running from source: no self-update
    d.skip()
    assert settings.value("updates/skip") == "99.0.0"
