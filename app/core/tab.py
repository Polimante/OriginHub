"""Base tab shared by every technique: sample table, preview plot, remove and export buttons."""
from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSplitter,
                             QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from core.dataset import Dataset, x_signature

PALETTE = ["#332288", "#CC6677", "#44AA99", "#DDCC77", "#882255",
           "#88CCEE", "#117733", "#999933", "#AA4499"]
BASE_COLS = ["Sample", "File", "Points", "X range", "X axis"]


def spin(lo, hi, val, dec, step, suffix=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    return s


class TechniqueTab(QWidget):
    """Subclasses add options, extra table columns and the preview of their technique."""

    x_label = "X"
    y_label = "Y"
    extra_columns: list[str] = []          # shown after BASE_COLS
    editable_extra: tuple[int, ...] = ()   # indices in extra_columns the user may edit

    def __init__(self, technique, main):
        super().__init__()
        self.technique, self.main = technique, main
        self.kind = technique.key
        self.datasets: list[Dataset] = []

        cols = BASE_COLS + self.extra_columns
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._item_changed)

        self.plot = pg.PlotWidget(background="w")
        self.plot.setLabel("bottom", self.x_label)
        self.plot.setLabel("left", self.y_label)
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.legend = self.plot.addLegend(offset=(-10, 10))

        btn_rm = QPushButton("Remove selected")
        btn_rm.clicked.connect(self.remove_selected)
        self.btn_export = QPushButton(f"Export {self.kind} to Origin")
        self.btn_export.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_export.clicked.connect(lambda: self.main.export(self))

        lay = QVBoxLayout(self)
        options = self.make_options()
        if options is not None:
            lay.addLayout(options)
        tools = QHBoxLayout()
        tools.addWidget(btn_rm)
        self.add_tools(tools)
        tools.addStretch()
        tools.addWidget(self.btn_export)

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.plot)
        split.setSizes([220, 430])
        lay.addWidget(split)
        lay.addLayout(tools)

    # ------------------------------------------------------------ hooks for subclasses
    def make_options(self):
        """Layout with the technique's options (above the table), or None."""
        return None

    def add_tools(self, tools: QHBoxLayout):
        """Extra widgets in the bottom bar (e.g. preview selector)."""

    def options(self) -> dict:
        """Passed to Technique.build_payload on export."""
        return {}

    def apply_material(self, values: dict):
        """Called when the user picks a material profile (values = this technique's section)."""

    def confirm_export(self, datasets: list[Dataset]) -> bool:
        """Last chance to warn the user; return False to cancel the export."""
        return True

    def extra_cells(self, ds: Dataset) -> list[str]:
        return [""] * len(self.extra_columns)

    def extra_edited(self, ds: Dataset, index: int, text: str):
        """The user edited extra column `index` of the row of `ds`."""

    def after_table_refresh(self):
        self.refresh_plot()

    def refresh_plot(self):
        raise NotImplementedError

    # ------------------------------------------------------------ data
    def color(self, i: int) -> str:
        return PALETTE[i % len(PALETTE)]

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

    def refresh_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.datasets))
        sigs = {}
        editable = {0} | {len(BASE_COLS) + j for j in self.editable_extra}
        for i, d in enumerate(self.datasets):
            sig = x_signature(d)
            xi = sigs.setdefault(sig, len(sigs) + 1)
            name = QTableWidgetItem(d.name)
            name.setFlags(name.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
            on = d.meta.get("on", True)
            name.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            name.setForeground(QColor(self.color(i)))
            cells = [name, QTableWidgetItem(d.source.name), QTableWidgetItem(str(len(d.x))),
                     QTableWidgetItem(f"{d.x[0]:g} – {d.x[-1]:g} (step {sig[2]:g})"),
                     QTableWidgetItem(f"X{xi}")]
            cells += [QTableWidgetItem(t) for t in self.extra_cells(d)]
            for j, c in enumerate(cells):
                if j not in editable:
                    c.setFlags(c.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, c)
        self.table.blockSignals(False)
        self.after_table_refresh()

    def set_cell(self, row: int, extra_index: int, text: str, color: str | None = None):
        """Updates an extra column without triggering extra_edited."""
        self.table.blockSignals(True)
        it = self.table.item(row, len(BASE_COLS) + extra_index)
        it.setText(text)
        if color:
            it.setForeground(QColor(color))
        self.table.blockSignals(False)

    def _item_changed(self, item: QTableWidgetItem):
        ds = self.datasets[item.row()]
        c = item.column()
        if c == 0:                              # rename the sample or (un)check it
            ds.name = item.text().strip() or ds.name
            ds.meta["on"] = item.checkState() == Qt.CheckState.Checked
            self.refresh_plot()
        elif c >= len(BASE_COLS):
            self.extra_edited(ds, c - len(BASE_COLS), item.text())


class BrokenTab(QWidget):
    """Shown instead of a technique that failed to load: the rest of the app keeps working."""

    def __init__(self, name: str, error: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"The '{name}' module could not be loaded. Other techniques are not affected.\n"
                             "Please report this error at github.com/Polimante/OriginHub/issues:"))
        view = QTextBrowser()
        view.setPlainText(error)
        lay.addWidget(view)
