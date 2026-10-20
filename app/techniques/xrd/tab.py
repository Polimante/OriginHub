"""XRD tab: preview of the patterns, optionally normalized and stacked."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QCheckBox

from core.tab import TechniqueTab


class XRDTab(TechniqueTab):
    x_label = "Diffraction Angle (2θ)"
    y_label = "Intensity (a.u.)"

    def add_tools(self, tools):
        self.chk_norm = QCheckBox("Normalized")
        self.chk_stack = QCheckBox("Stacked")
        self.chk_stack.setChecked(True)
        for c in (self.chk_norm, self.chk_stack):
            c.toggled.connect(self.refresh_plot)
            tools.addWidget(c)

    def refresh_plot(self):
        self.plot.clear()
        self.legend.clear()
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
            self.plot.plot(d.x, y, pen=pg.mkPen(self.color(i), width=1.5), name=d.name)
