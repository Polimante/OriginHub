"""UV-Vis tab: baseline / Tauc options, per-sample thickness and range, Eg and E_U preview."""
from __future__ import annotations

import re

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton

from core.tab import TechniqueTab, spin

from . import analysis as an

VIEWS = ["Raw", "Baseline", "Transmittance", "Tauc", "Urbach"]
D, RANGE, EG, EU = 0, 1, 2, 3           # extra columns


class UVVisTab(TechniqueTab):
    x_label = "Wavelength (nm)"
    y_label = "Absorbance (a.u.)"
    extra_columns = ["Thickness (nm)", "Tauc range (nm)", "Eg (eV)", "E_U (meV)"]
    editable_extra = (D, RANGE)

    def __init__(self, technique, main):
        self.results: dict[int, an.TaucResult] = {}
        self.edge = {"edge_min_nm": 300.0, "edge_window_nm": 45.0}    # from the material profile
        super().__init__(technique, main)

    # ------------------------------------------------------------ options
    def make_options(self):
        self.ref = spin(200, 3000, 850, 1, 5, " nm")
        self.ref.setToolTip("Each spectrum has its value at this wavelength subtracted "
                            "(mean within ±2 nm). Use a region where the sample does not absorb.")
        self.chk_tauc = QCheckBox("Tauc + Urbach")
        self.chk_tauc.setChecked(True)
        self.trans = QComboBox()
        self.trans.addItems(list(an.TRANSITIONS))
        self.a_max = spin(0.5, 10, 3.0, 1, 0.5)
        self.a_max.setToolTip("Points whose raw absorbance is above this value (detector "
                              "saturation) are excluded from Tauc and Urbach.")
        self.d_all = spin(0, 100000, 0, 0, 10, " nm")
        self.d_all.setSpecialValueText("—")
        btn_d = QPushButton("Apply to all")
        btn_d.clicked.connect(self._apply_d_all)
        btn_auto = QPushButton("Auto range")
        btn_auto.setToolTip("Finds the absorption edge with the longest wavelength "
                            "(e.g. the perovskite, not residual PbI₂) and uses a window around it "
                            "(width set by the material profile).")
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

    def add_tools(self, tools):
        self.view = QComboBox()
        self.view.addItems(VIEWS)
        self.view.currentIndexChanged.connect(self.refresh_plot)
        tools.addWidget(QLabel("Preview:"))
        tools.addWidget(self.view)

    def options(self) -> dict:
        return {"ref_nm": self.ref.value(), "a_max": self.a_max.value(),
                "tauc": self.chk_tauc.isChecked(),
                "n": an.TRANSITIONS[self.trans.currentText()], **self.edge}

    def apply_material(self, values: dict):
        widgets = (self.ref, self.a_max, self.trans)
        for w in widgets:
            w.blockSignals(True)
        self.ref.setValue(values["baseline_nm"])
        self.a_max.setValue(values["a_max"])
        self.trans.setCurrentText(an.TRANSITION_IDS[values["transition"]])
        for w in widgets:
            w.blockSignals(False)
        self.edge = {"edge_min_nm": values["edge_min_nm"], "edge_window_nm": values["edge_window_nm"]}
        for ds in self.datasets:                    # automatic ranges follow the new material
            if ds.meta.get("tauc_range_auto", True):
                ds.meta["tauc_range"] = None
        self.refresh_table()

    def confirm_export(self, datasets):
        if self.chk_tauc.isChecked():
            no_d = [d.name for d in datasets if not d.meta.get("d_nm")]
            if no_d and len(no_d) < len(datasets):
                QMessageBox.information(
                    self, "OriginHub",
                    "Some samples have no thickness. α will be in arbitrary units "
                    "for all of them (Eg and E_U do not change).\n\nWithout thickness: " + ", ".join(no_d))
        return True

    def _apply_d_all(self):
        d = self.d_all.value() or None
        for ds in self.datasets:
            ds.meta["d_nm"] = d
        self.refresh_table()

    def _auto_ranges(self):
        for ds in self.datasets:
            ds.meta["tauc_range"] = None
        self.refresh_table()

    # ------------------------------------------------------------ table
    def extra_cells(self, d):
        dn = d.meta.get("d_nm")
        rng = d.meta.get("tauc_range")
        return [f"{dn:g}" if dn else "", f"{rng[0]:.0f}-{rng[1]:.0f}" if rng else "", "", ""]

    def extra_edited(self, ds, index, text):
        if index == D:
            try:
                ds.meta["d_nm"] = float(text.replace(",", ".")) if text.strip() else None
            except ValueError:
                ds.meta["d_nm"] = None
        elif index == RANGE:
            m = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*(?:-|–|to)\s*(\d+(?:[.,]\d+)?)", text)
            ds.meta["tauc_range"] = ((float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", ".")))
                                     if m else None)
            ds.meta["tauc_range_auto"] = not m
        self.recompute()

    def after_table_refresh(self):
        self.recompute()

    def recompute(self):
        """Preview Tauc/Urbach (the official values are Origin's fits, on the same rows)."""
        self.results.clear()
        if self.chk_tauc.isChecked():
            o = self.options()
            use_d = all(d.meta.get("d_nm") for d in self.datasets)
            for i, ds in enumerate(self.datasets):
                y_corr, _ = an.baseline(ds.x, ds.y, o["ref_nm"])
                if not ds.meta.get("tauc_range"):
                    ds.meta["tauc_range"] = an.suggest_range(ds.x, y_corr, ds.y, o["a_max"],
                                                             width=o["edge_window_nm"], lam_min=o["edge_min_nm"])
                    ds.meta["tauc_range_auto"] = True
                self.results[i] = an.tauc_analysis(ds.x, ds.y, y_corr, o["n"],
                                                   ds.meta.get("d_nm") if use_d else None,
                                                   ds.meta["tauc_range"], o["a_max"])
        self._fill_results()
        self.refresh_plot()

    def _fill_results(self):
        for i, ds in enumerate(self.datasets):
            r = self.results.get(i)
            rng = ds.meta.get("tauc_range")
            self.set_cell(i, RANGE, f"{rng[0]:.0f}-{rng[1]:.0f}" if rng else "")
            eg = r.eg if r else None
            self.set_cell(i, EG, f"{eg:.3f}" if eg else "—")
            if r and r.eu_mev:
                self.set_cell(i, EU, f"{r.eu_mev:.1f}" + ("" if r.urbach_ok else "  (unreliable)"),
                              "black" if r.urbach_ok else "gray")
            else:
                self.set_cell(i, EU, "—")

    # ------------------------------------------------------------ preview
    def refresh_plot(self):
        self.plot.clear()
        self.legend.clear()
        view = self.view.currentText()
        o = self.options()
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
            pen = pg.mkPen(self.color(i), width=1.5)
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
