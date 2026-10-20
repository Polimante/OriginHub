"""OriginHub - loads raw data, shows a preview and sends it to Origin.

The techniques (UV-Vis, XRD, ...) are plugins in app/techniques/; this window only
hosts their tabs, routes files to the right one and launches Origin.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                             QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QStatusBar, QTabWidget,
                             QTextBrowser, QVBoxLayout, QWidget)

from core import origin_bridge as ob
from core.materials import load_materials
from core.registry import discover
from core.tab import BrokenTab
from version import __version__

APP_DIR = Path(__file__).resolve().parent
# source checkout: HELP.md is next to app/; installed (PyInstaller): it is bundled next to main
HELP_FILE = next((p for p in (APP_DIR / "HELP.md", APP_DIR.parent / "HELP.md") if p.is_file()),
                 APP_DIR.parent / "HELP.md")


class HelpDialog(QDialog):
    """Shows HELP.md (usage guide and references) rendered as Markdown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OriginHub - Help")
        self.resize(820, 720)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        try:
            view.setMarkdown(HELP_FILE.read_text(encoding="utf-8"))
        except OSError:
            view.setPlainText(f"Help file not found: {HELP_FILE}")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(view)
        lay.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self, registry=None):
        super().__init__()
        self.setWindowTitle(f"OriginHub {__version__}")
        self.resize(1200, 820)
        self.setAcceptDrops(True)

        # ---- techniques: a plugin that fails shows an error tab, the others keep working
        self.registry = registry or discover()
        self.tabs = QTabWidget()
        self.kind_tabs = {}
        for key, t in self.registry.techniques.items():
            try:
                tab = t.make_tab(self)
            except Exception:
                import traceback
                self.tabs.addTab(BrokenTab(t.title, traceback.format_exc()), f"⚠ {t.title}")
                continue
            self.kind_tabs[key] = tab
            self.tabs.addTab(tab, t.title)
        for name, err in self.registry.failures.items():
            self.tabs.addTab(BrokenTab(name, err), f"⚠ {name}")

        # ---- material profiles
        self.materials, self.material_errors = load_materials(self.registry.techniques.values())
        self.material_box = QComboBox()
        for m in self.materials:
            self.material_box.addItem(m.name)
            self.material_box.setItemData(self.material_box.count() - 1, m.description,
                                          Qt.ItemDataRole.ToolTipRole)
        self.material_box.setToolTip("Analysis defaults for this material (app/materials/*.toml)")
        self.material_box.currentIndexChanged.connect(self.apply_material)

        btn_files = QPushButton("Add files…")
        btn_files.clicked.connect(self.pick_files)
        btn_dir = QPushButton("Add folder…")
        btn_dir.clicked.connect(self.pick_dir)

        self.origin_box = QComboBox()
        for ver, exe in ob.find_origins():
            self.origin_box.addItem(f"Origin {ver}", str(exe))
        if not self.origin_box.count():
            self.origin_box.addItem("Origin not found", "")

        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText("Folder to save the .opju (default: the data folder)")
        btn_out = QPushButton("…")
        btn_out.setFixedWidth(30)
        btn_out.clicked.connect(self.pick_out)
        btn_help = QPushButton("Help")
        btn_help.setToolTip("How to use OriginHub, what each analysis does, and references")
        btn_help.clicked.connect(lambda: HelpDialog(self).exec())

        top = QHBoxLayout()
        top.addWidget(btn_files)
        top.addWidget(btn_dir)
        top.addSpacing(20)
        top.addWidget(QLabel("Material:"))
        top.addWidget(self.material_box)
        top.addSpacing(10)
        top.addWidget(QLabel("Version:"))
        top.addWidget(self.origin_box)
        top.addSpacing(10)
        top.addWidget(QLabel("Save to:"))
        top.addWidget(self.out_dir, 1)
        top.addWidget(btn_out)
        top.addSpacing(10)
        top.addWidget(btn_help)

        hint = QLabel("Drag files or folders onto this window. Each file type is recognized from its content.")
        hint.setStyleSheet("color: gray;")

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(top)
        lay.addWidget(hint)
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

        self._watch: list[tuple[Path, float, str]] = []
        self._timer = QTimer(self, interval=1500, timeout=self._poll_logs)

        if self.materials:
            self.apply_material()
        if self.material_errors:
            self.statusBar().showMessage(f"{len(self.material_errors)} material profile(s) ignored "
                                         "(hover for details).", 15000)
            self.statusBar().setToolTip("\n".join(f"{k}: {v}" for k, v in self.material_errors.items()))

    # ------------------------------------------------------------ material
    def current_material(self):
        i = self.material_box.currentIndex()
        return self.materials[i] if 0 <= i < len(self.materials) else None

    def apply_material(self, *_):
        mat = self.current_material()
        if not mat:
            return
        for key, tab in self.kind_tabs.items():
            try:
                tab.apply_material(mat.for_technique(self.registry.techniques[key]))
            except Exception as ex:                 # a technique's bug must not block the others
                self.statusBar().showMessage(f"{key}: could not apply material {mat.name} ({ex})", 10000)

    # ------------------------------------------------------------ load
    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Measurement files", "",
                                                "Data (*.txt *.sd *.xls *.xlsx *.csv *.dat);;All (*.*)")
        self.load_paths([Path(f) for f in files])

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Folder with measurement files")
        if d:
            self.load_paths([Path(d)])

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Folder to save the Origin projects")
        if d:
            self.out_dir.setText(d)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.load_paths([Path(u.toLocalFile()) for u in e.mimeData().urls()])

    def load_paths(self, paths: list[Path]):
        files = []
        for p in paths:
            files += sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p]
        loaded, skipped, touched, last = 0, [], set(), None
        for f in files:
            try:
                hit = self.registry.identify(f)
                if not hit:
                    skipped.append(f.name)
                    continue
                if hit[0].key not in self.kind_tabs:
                    skipped.append(f"{f.name} ({hit[0].title} module unavailable)")
                    continue
                t, out = self.registry.load(f)
                self.kind_tabs[t.key].datasets += out
                loaded += len(out)
                touched.add(t.key)
                last = t.key
            except Exception as ex:
                skipped.append(f"{f.name} ({ex})")
        for key in touched:
            try:
                self.kind_tabs[key].refresh_table()
            except Exception as ex:
                skipped.append(f"{key} preview failed ({ex})")
        if last:
            self.tabs.setCurrentWidget(self.kind_tabs[last])
        msg = f"{loaded} sample(s) loaded."
        if skipped:
            msg += f" Skipped: {len(skipped)}"
            self.statusBar().setToolTip("\n".join(skipped))
        self.statusBar().showMessage(msg, 8000)

    # ------------------------------------------------------------ export
    def export(self, tab):
        data = tab.checked()
        if not data:
            QMessageBox.information(self, "OriginHub", "No sample is checked.")
            return
        exe = self.origin_box.currentData()
        if not exe:
            QMessageBox.warning(self, "OriginHub", "No Origin installation found.")
            return
        if not tab.confirm_export(data):
            return
        out = Path(self.out_dir.text()) if self.out_dir.text() else data[0].source.parent
        save = out / f"{tab.kind}_{time.strftime('%Y%m%d_%H%M%S')}.opju"
        try:
            payload = ob.build_payload(tab.technique, data, save, tab.options())
            mat = self.current_material()
            payload["material"] = mat.name if mat else ""
            _, log = ob.launch(payload, tab.technique, Path(exe))
        except Exception as ex:
            QMessageBox.critical(self, "OriginHub", str(ex))
            return
        self._watch.append((log, time.time(), save.name))
        self._timer.start()
        self.statusBar().showMessage(f"Opening {self.origin_box.currentText()} and building {save.name}…")

    def _poll_logs(self):
        for item in list(self._watch):
            log, t0, name = item
            text = log.read_text(encoding="utf-8") if log.exists() else ""
            if "OK" in text.splitlines():
                self.statusBar().showMessage(f"Done: {name}", 10000)
            elif "Traceback" in text:
                QMessageBox.critical(self, "Error in Origin", text[-1500:])
            elif time.time() - t0 < 300:
                continue
            self._watch.remove(item)
        if not self._watch:
            self._timer.stop()


def check(report: Path | None = None) -> int:
    """`--check [report.txt]`: loads every technique and material profile without opening a window.

    Used to smoke-test the installed/frozen app (are all bundled files found?). Exit code 0 = OK.
    The installed app has no console, so the report can also be written to a file.
    """
    from core.materials import load_materials
    reg = discover()
    mats, mat_errors = load_materials(reg.techniques.values())
    lines = [f"OriginHub {__version__}"]
    lines += [f"  technique {t.key}: {len(t.readers)} reader(s), Origin script {t.origin_script.name}"
              for t in reg.techniques.values()]
    lines.append(f"  materials: {', '.join(m.name for m in mats)}")
    lines.append(f"  Origin helpers: {ob.ORIGIN_COMMON.is_file()}  help: {HELP_FILE.is_file()}")
    problems = [f"technique {k}: {v.strip().splitlines()[-1]}" for k, v in reg.failures.items()]
    problems += [f"material {k}: {v}" for k, v in mat_errors.items()]
    if not ob.ORIGIN_COMMON.is_file():
        problems.append(f"missing {ob.ORIGIN_COMMON}")
    if not HELP_FILE.is_file():
        problems.append(f"missing {HELP_FILE}")
    if not reg.techniques:
        problems.append("no technique loaded")
    lines += [f"PROBLEM: {p}" for p in problems]
    lines.append("OK" if not problems else "FAILED")
    text = "\n".join(lines)
    print(text)                                   # no-op in the windowed exe (no console)
    if report:
        report.write_text(text + "\n", encoding="utf-8")
    return 1 if problems else 0


def main():
    if "--check" in sys.argv:
        rest = sys.argv[sys.argv.index("--check") + 1:]
        sys.exit(check(Path(rest[0]) if rest else None))
    if "--version" in sys.argv:
        print(__version__)
        sys.exit(0)
    pg.setConfigOptions(antialias=True)
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1:
        w.load_paths([Path(a) for a in sys.argv[1:]])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
