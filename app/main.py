"""OriginHub - loads raw data (ABS, XRD), shows a preview and sends it to Origin."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                             QLineEdit, QMainWindow, QMessageBox, QPushButton, QSplitter,
                             QStatusBar, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser,
                             QVBoxLayout, QWidget)

import analysis as an
import origin_bridge as ob
import parsers
from parsers import ABS, XRD, Dataset

HELP_FILE = Path(__file__).resolve().parent.parent / "HELP.md"
PALETTE = ["#332288", "#CC6677", "#44AA99", "#DDCC77", "#882255",
           "#88CCEE", "#117733", "#999933", "#AA4499"]
KIND_INFO = {
    ABS: ("UV-Vis (ABS)", "Wavelength (nm)", "Absorbance (a.u.)"),
    XRD: ("XRD", "Diffraction Angle (2θ)", "Intensity (a.u.)"),
}
BASE_COLS = ["Sample", "File", "Points", "X range", "X axis"]
ABS_COLS = ["Thickness (nm)", "Tauc range (nm)", "Eg (eV)", "E_U (meV)"]
C_D, C_RANGE, C_EG, C_EU = 5, 6, 7, 8          # extra columns of the ABS tab
ABS_VIEWS = ["Raw", "Baseline", "Transmittance", "Tauc", "Urbach"]


def _spin(lo, hi, val, dec, step, suffix=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    return s


class KindTab(QWidget):
    """One tab per measurement type: sample table + preview + export."""

    def __init__(self, kind: str, main: "MainWindow"):
        super().__init__()
        self.kind, self.main = kind, main
        self.datasets: list[Dataset] = []
        self.results: dict[int, an.TaucResult] = {}

        cols = BASE_COLS + (ABS_COLS if kind == ABS else [])
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._item_changed)

        _, xl, yl = KIND_INFO[kind]
        self.plot = pg.PlotWidget(background="w")
        self.plot.setLabel("bottom", xl)
        self.plot.setLabel("left", yl)
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.legend = self.plot.addLegend(offset=(-10, 10))

        btn_rm = QPushButton("Remove selected")
        btn_rm.clicked.connect(self.remove_selected)
        self.btn_export = QPushButton(f"Export {kind} to Origin")
        self.btn_export.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_export.clicked.connect(lambda: self.main.export(self))

        tools = QHBoxLayout()
        tools.addWidget(btn_rm)
        lay = QVBoxLayout(self)
        if kind == XRD:
            self.chk_norm = QCheckBox("Normalized")
            self.chk_stack = QCheckBox("Stacked")
            self.chk_stack.setChecked(True)
            for c in (self.chk_norm, self.chk_stack):
                c.toggled.connect(self.refresh_plot)
                tools.addWidget(c)
        else:
            lay.addLayout(self._abs_options())
            self.view = QComboBox()
            self.view.addItems(ABS_VIEWS)
            self.view.currentIndexChanged.connect(self.refresh_plot)
            tools.addWidget(QLabel("Preview:"))
            tools.addWidget(self.view)
        tools.addStretch()
        tools.addWidget(self.btn_export)

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.plot)
        split.setSizes([220, 430])
        lay.addWidget(split)
        lay.addLayout(tools)

    # ------------------------------------------------------------ ABS options
    def _abs_options(self):
        self.ref = _spin(200, 3000, 850, 1, 5, " nm")
        self.ref.setToolTip("Each spectrum has its value at this wavelength subtracted "
                            "(mean within ±2 nm). Use a region where the sample does not absorb.")
        self.chk_tauc = QCheckBox("Tauc + Urbach")
        self.chk_tauc.setChecked(True)
        self.trans = QComboBox()
        self.trans.addItems(list(an.TRANSITIONS))
        self.a_max = _spin(0.5, 10, 3.0, 1, 0.5)
        self.a_max.setToolTip("Points whose raw absorbance is above this value (detector "
                              "saturation) are excluded from Tauc and Urbach.")
        self.d_all = _spin(0, 100000, 0, 0, 10, " nm")
        self.d_all.setSpecialValueText("—")
        btn_d = QPushButton("Apply to all")
        btn_d.clicked.connect(self._apply_d_all)
        btn_auto = QPushButton("Auto range")
        btn_auto.setToolTip("Finds the absorption edge with the longest wavelength "
                            "(the perovskite, not residual PbI₂) and uses ±45 nm around it.")
        btn_auto.clicked.connect(self._auto_ranges)
        for w in (self.ref, self.a_max):
            w.valueChanged.connect(self.recompute)
        self.chk_tauc.toggled.connect(self.recompute)
        self.trans.currentIndexChanged.connect(self.recompute)

        row = QHBoxLayout()
        row.addWidget(QLabel("Baseline at"))
        row.addWidget(self.ref)
        row.addSpacing(16)
        row.addWidget(self.chk_tauc)
        row.addWidget(self.trans)
        row.addWidget(QLabel("A max"))
        row.addWidget(self.a_max)
        row.addSpacing(16)
        row.addWidget(QLabel("Thickness"))
        row.addWidget(self.d_all)
        row.addWidget(btn_d)
        row.addWidget(btn_auto)
        row.addStretch()
        return row

    def abs_opts(self) -> dict:
        return {"ref_nm": self.ref.value(), "a_max": self.a_max.value(),
                "tauc": self.chk_tauc.isChecked(),
                "n": an.TRANSITIONS[self.trans.currentText()]}

    def _apply_d_all(self):
        d = self.d_all.value() or None
        for ds in self.datasets:
            ds.meta["d_nm"] = d
        self.refresh_table()

    def _auto_ranges(self):
        for ds in self.datasets:
            ds.meta["tauc_range"] = None
        self.refresh_table()

    # ------------------------------------------------------------ data
    def add(self, ds: Dataset):
        self.datasets.append(ds)
        self.refresh_table()

    def is_checked(self, i: int) -> bool:
        it = self.table.item(i, 0)
        return bool(it) and it.checkState() == Qt.CheckState.Checked

    def checked(self) -> list[Dataset]:
        return [d for i, d in enumerate(self.datasets) if self.is_checked(i)]

    def remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.datasets[r]
        self.refresh_table()

    def recompute(self):
        """Preview Tauc/Urbach (the official values are Origin's fits, on the same rows)."""
        self.results.clear()
        if self.kind == ABS and self.chk_tauc.isChecked():
            o = self.abs_opts()
            use_d = all(d.meta.get("d_nm") for d in self.datasets)
            for i, ds in enumerate(self.datasets):
                y_corr, _ = an.baseline(ds.x, ds.y, o["ref_nm"])
                if not ds.meta.get("tauc_range"):
                    ds.meta["tauc_range"] = an.suggest_range(ds.x, y_corr, ds.y, o["a_max"])
                self.results[i] = an.tauc_analysis(ds.x, ds.y, y_corr, o["n"],
                                                   ds.meta.get("d_nm") if use_d else None,
                                                   ds.meta["tauc_range"], o["a_max"])
        self._fill_results()
        self.refresh_plot()

    def refresh_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.datasets))
        sigs = {}
        for i, d in enumerate(self.datasets):
            sig = parsers.x_signature(d)
            xi = sigs.setdefault(sig, len(sigs) + 1)
            name = QTableWidgetItem(d.name)
            name.setFlags(name.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
            on = d.meta.get("on", True)
            name.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            name.setForeground(QColor(PALETTE[i % len(PALETTE)]))
            cells = [name, QTableWidgetItem(d.source.name), QTableWidgetItem(str(len(d.x))),
                     QTableWidgetItem(f"{d.x[0]:g} – {d.x[-1]:g} (step {sig[2]:g})"),
                     QTableWidgetItem(f"X{xi}")]
            if self.kind == ABS:
                dn = d.meta.get("d_nm")
                rng = d.meta.get("tauc_range")
                cells += [QTableWidgetItem(f"{dn:g}" if dn else ""),
                          QTableWidgetItem(f"{rng[0]:.0f}-{rng[1]:.0f}" if rng else ""),
                          QTableWidgetItem(""), QTableWidgetItem("")]
            for j, c in enumerate(cells):
                if j not in (0, C_D, C_RANGE):
                    c.setFlags(c.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, c)
        self.table.blockSignals(False)
        if self.kind == ABS:
            self.recompute()
        else:
            self.refresh_plot()

    def _fill_results(self):
        if self.kind != ABS:
            return
        self.table.blockSignals(True)
        for i, ds in enumerate(self.datasets):
            r = self.results.get(i)
            rng = ds.meta.get("tauc_range")
            self.table.item(i, C_RANGE).setText(f"{rng[0]:.0f}-{rng[1]:.0f}" if rng else "")
            eg = r.eg if r else None
            self.table.item(i, C_EG).setText(f"{eg:.3f}" if eg else "—")
            eu = self.table.item(i, C_EU)
            if r and r.eu_mev:
                eu.setText(f"{r.eu_mev:.1f}" + ("" if r.urbach_ok else "  (unreliable)"))
                eu.setForeground(QColor("black" if r.urbach_ok else "gray"))
            else:
                eu.setText("—")
            for c in (C_EG, C_EU):
                self.table.item(i, c).setFlags(self.table.item(i, c).flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.blockSignals(False)

    def _item_changed(self, item: QTableWidgetItem):
        ds = self.datasets[item.row()]
        c = item.column()
        if c == 0:                              # rename the sample or (un)check it
            ds.name = item.text().strip() or ds.name
            ds.meta["on"] = item.checkState() == Qt.CheckState.Checked
            self.refresh_plot()
        elif c == C_D and self.kind == ABS:
            try:
                ds.meta["d_nm"] = float(item.text().replace(",", ".")) if item.text().strip() else None
            except ValueError:
                ds.meta["d_nm"] = None
            self.recompute()
        elif c == C_RANGE and self.kind == ABS:
            m = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*(?:-|–|to)\s*(\d+(?:[.,]\d+)?)", item.text())
            ds.meta["tauc_range"] = ((float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", ".")))
                                     if m else None)
            self.recompute()

    # ------------------------------------------------------------ preview
    def refresh_plot(self):
        self.plot.clear()
        self.legend.clear()
        if self.kind == XRD:
            self._plot_xrd()
        else:
            self._plot_abs()

    def _plot_xrd(self):
        offset = 0.0
        norm, stack = self.chk_norm.isChecked(), self.chk_stack.isChecked()
        for i, d in enumerate(self.datasets):
            if not self.is_checked(i):
                continue
            y = d.y.astype(float)
            if norm:
                lo, hi = np.nanmin(y), np.nanmax(y)
                y = (y - lo) / ((hi - lo) or 1)
            if stack:
                y = y - np.nanmin(y) + offset
                offset = np.nanmax(y) * 1.05 if not norm else offset + 1.1
            self.plot.plot(d.x, y, pen=pg.mkPen(PALETTE[i % len(PALETTE)], width=1.5), name=d.name)

    def _plot_abs(self):
        view = self.view.currentText()
        o = self.abs_opts()
        labels = {"Raw": ("Wavelength (nm)", "Absorbance (a.u.)"),
                  "Baseline": ("Wavelength (nm)", f"Absorbance − A({o['ref_nm']:g} nm)"),
                  "Transmittance": ("Wavelength (nm)", "Transmittance (%)"),
                  "Tauc": ("Photon energy (eV)", f"(αhν)^{an.EXPONENT_LABEL[o['n']]} (normalized)"),
                  "Urbach": ("Photon energy (eV)", "ln α")}
        self.plot.setLabel("bottom", labels[view][0])
        self.plot.setLabel("left", labels[view][1])
        for i, d in enumerate(self.datasets):
            if not self.is_checked(i):
                continue
            pen = pg.mkPen(PALETTE[i % len(PALETTE)], width=1.5)
            if view in ("Raw", "Baseline", "Transmittance"):
                y = d.y if view == "Raw" else (
                    an.baseline(d.x, d.y, o["ref_nm"])[0] if view == "Baseline" else an.transmittance(d.y))
                self.plot.plot(d.x, y, pen=pen, name=d.name)
                continue
            r = self.results.get(i)
            if not r:
                continue
            fit = pg.mkPen("k", width=1.5, style=Qt.PenStyle.DashLine)
            if view == "Tauc" and r.tauc:
                lo, hi = r.tauc.rows
                scale = np.nanmax(r.ty[lo - 1:hi]) or 1      # each curve normalized by the top of its window
                self.plot.plot(r.e, r.ty / scale, pen=pen, name=f"{d.name}  Eg = {r.eg:.3f} eV")
                e_hi = r.e[lo - 1:hi].max()
                ex = np.array([r.eg, e_hi + 0.3 * (e_hi - r.eg)])
                self.plot.plot(ex, (r.tauc.a + r.tauc.b * ex) / scale, pen=fit)
            elif view == "Urbach" and r.urbach:
                ok = np.isfinite(r.ln_alpha)
                tag = "" if r.urbach_ok else " (unreliable)"
                self.plot.plot(r.e[ok], r.ln_alpha[ok], pen=pen, name=f"{d.name}  E_U = {r.eu_mev:.1f} meV{tag}")
                lo, hi = r.urbach.rows
                ue = r.e[lo - 1:hi]
                ex = np.array([ue.min() - 0.02, ue.max() + 0.02])
                self.plot.plot(ex, r.urbach.a + r.urbach.b * ex, pen=fit)
        if view in ("Tauc", "Urbach"):
            egs = [r.eg for i, r in self.results.items() if r.eg and self.is_checked(i)]
            if egs:
                lo_e, hi_e = (min(egs) - 0.25, max(egs) + 0.45) if view == "Tauc" else (min(egs) - 0.2, max(egs) + 0.1)
                self.plot.setXRange(lo_e, hi_e)
                if view == "Tauc":
                    self.plot.setYRange(0, 1.5)
                else:
                    self.plot.enableAutoRange(axis="y")
        else:
            self.plot.enableAutoRange()


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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OriginHub")
        self.resize(1200, 820)
        self.setAcceptDrops(True)

        self.tabs = QTabWidget()
        self.kind_tabs = {k: KindTab(k, self) for k in (ABS, XRD)}
        for k, t in self.kind_tabs.items():
            self.tabs.addTab(t, KIND_INFO[k][0])

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
        loaded, skipped, last = 0, [], None
        for f in files:
            try:
                kind = parsers.detect(f)
                if kind not in self.kind_tabs:
                    skipped.append(f.name)
                    continue
                for ds in parsers.load(f):
                    self.kind_tabs[kind].datasets.append(ds)
                    loaded += 1
                last = kind
            except Exception as ex:
                skipped.append(f"{f.name} ({ex})")
        for t in self.kind_tabs.values():
            t.refresh_table()
        if last:
            self.tabs.setCurrentWidget(self.kind_tabs[last])
        msg = f"{loaded} sample(s) loaded."
        if skipped:
            msg += f" Skipped: {len(skipped)}"
            self.statusBar().setToolTip("\n".join(skipped))
        self.statusBar().showMessage(msg, 8000)

    # ------------------------------------------------------------ export
    def export(self, tab: KindTab):
        data = tab.checked()
        if not data:
            QMessageBox.information(self, "OriginHub", "No sample is checked.")
            return
        exe = self.origin_box.currentData()
        if not exe:
            QMessageBox.warning(self, "OriginHub", "No Origin installation found.")
            return
        opts = tab.abs_opts() if tab.kind == ABS else None
        if opts and opts["tauc"]:
            no_d = [d.name for d in data if not d.meta.get("d_nm")]
            if no_d and len(no_d) < len(data):
                QMessageBox.information(
                    self, "OriginHub",
                    "Some samples have no thickness. α will be in arbitrary units "
                    "for all of them (Eg and E_U do not change).\n\nWithout thickness: " + ", ".join(no_d))
        out = Path(self.out_dir.text()) if self.out_dir.text() else data[0].source.parent
        save = out / f"{tab.kind}_{time.strftime('%Y%m%d_%H%M%S')}.opju"
        try:
            payload = ob.build_payload(tab.kind, data, save, abs_opts=opts)
            _, log = ob.launch(payload, Path(exe))
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


def main():
    pg.setConfigOptions(antialias=True)
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1:
        w.load_paths([Path(a) for a in sys.argv[1:]])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
