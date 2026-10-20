"""Update and setup-check dialogs. Network work runs in a background thread so the window never freezes."""
from __future__ import annotations

import threading
import webbrowser

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                             QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
                             QTextBrowser, QVBoxLayout)

from core import environment as env
from core import updater
from version import __version__

STATUS_COLOR = {"ok": "#117733", "warning": "#AA7700", "error": "#CC3311"}
STATUS_TEXT = {"ok": "OK", "warning": "Attention", "error": "Problem"}


class Worker(QObject):
    """Runs fn(*args) in a thread; results come back on the GUI thread through signals."""
    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, fn, *args, with_progress=False):
        super().__init__()
        self.fn, self.args, self.with_progress = fn, args, with_progress

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            kw = {"progress": lambda d, t: self.progress.emit(d, t)} if self.with_progress else {}
            self.done.emit(self.fn(*self.args, **kw))
        except Exception as ex:
            self.failed.emit(str(ex))


# ------------------------------------------------------------ updates
class UpdateDialog(QDialog):
    """Shows what's new; downloads, verifies and installs the update (installed app) or opens the page."""

    def __init__(self, release: updater.Release, settings, parent=None):
        super().__init__(parent)
        self.release, self.settings = release, settings
        self.setWindowTitle("OriginHub - update available")
        self.resize(620, 520)
        head = QLabel(f"<b>OriginHub {release.version}</b> is available (you have {__version__}).")
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown("### What's new\n\n" + (release.notes or "_No notes._"))
        self.bar = QProgressBar()
        self.bar.hide()
        self.status = QLabel("")
        self.auto = QCheckBox("Check for updates when OriginHub starts")
        self.auto.setChecked(settings.value("updates/auto", True, type=bool))
        self.auto.toggled.connect(lambda v: settings.setValue("updates/auto", v))

        self.btn_go = QPushButton("Download and install" if updater.can_self_update() else "Open download page")
        self.btn_go.setDefault(True)
        self.btn_go.clicked.connect(self.go)
        btn_skip = QPushButton("Skip this version")
        btn_skip.clicked.connect(self.skip)
        btn_later = QPushButton("Later")
        btn_later.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.auto)
        buttons.addStretch()
        for b in (btn_skip, btn_later, self.btn_go):
            buttons.addWidget(b)

        lay = QVBoxLayout(self)
        lay.addWidget(head)
        if not updater.can_self_update():
            lay.addWidget(QLabel("You are running OriginHub from source: update with <code>git pull</code>, "
                                 "or install the Windows version from the download page."))
        lay.addWidget(notes, 1)
        lay.addWidget(self.bar)
        lay.addWidget(self.status)
        lay.addLayout(buttons)

    def skip(self):
        self.settings.setValue("updates/skip", self.release.version)
        self.reject()

    def go(self):
        if not updater.can_self_update():
            webbrowser.open(self.release.page_url)
            self.accept()
            return
        self.btn_go.setEnabled(False)
        self.bar.show()
        self.status.setText("Downloading…")
        self.worker = Worker(updater.download, self.release, with_progress=True)
        self.worker.progress.connect(self._progress)
        self.worker.done.connect(self._install)
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def _progress(self, done, total):
        self.bar.setMaximum(total or 0)
        self.bar.setValue(done)

    def _failed(self, msg):
        self.status.setText("")
        self.bar.hide()
        self.btn_go.setEnabled(True)
        QMessageBox.warning(self, "OriginHub", f"The update could not be installed:\n\n{msg}\n\n"
                            f"You can download it manually from {updater.RELEASES_PAGE}")

    def _install(self, installer):
        self.status.setText("Verified. Installing - OriginHub will restart…")
        try:
            updater.launch_installer(installer)
        except Exception as ex:
            self._failed(str(ex))
            return
        QApplication.quit()


def check_for_updates(parent, settings, manual: bool):
    """Background check; shows UpdateDialog if there is something new.

    manual=False (at start-up): silent when offline, up to date or the version was skipped.
    """
    def found(rel):
        if rel is None:
            if manual:
                QMessageBox.information(parent, "OriginHub", f"OriginHub {__version__} is up to date.")
            return
        if not manual and settings.value("updates/skip", "") == rel.version:
            return
        UpdateDialog(rel, settings, parent).exec()

    def failed(msg):
        if manual:
            QMessageBox.warning(parent, "OriginHub", f"Could not check for updates: {msg}")

    worker = Worker(updater.check)
    worker.done.connect(found)
    worker.failed.connect(failed)
    parent._update_worker = worker              # keep a reference while the thread runs
    worker.start()


# ------------------------------------------------------------ setup check
class SetupDialog(QDialog):
    """Lists what OriginHub needs outside itself; offers fixes, which run only when clicked."""

    def __init__(self, settings, parent=None, work=None):
        super().__init__(parent)
        self.settings, self.work = settings, work
        self.setWindowTitle("OriginHub - setup check")
        self.resize(760, 360)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Item", "Status", "Details", ""])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(2, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setWordWrap(True)
        self.auto = QCheckBox("Check for updates when OriginHub starts")
        self.auto.setChecked(settings.value("updates/auto", True, type=bool))
        self.auto.toggled.connect(lambda v: settings.setValue("updates/auto", v))
        btn_again = QPushButton("Check again")
        btn_again.clicked.connect(self.refresh)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addWidget(self.auto)
        bottom.addStretch()
        bottom.addWidget(btn_again)
        bottom.addWidget(box)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"OriginHub {__version__}: things it needs outside the app. "
                             "Nothing is changed on your computer unless you click a button."))
        lay.addWidget(self.table, 1)
        lay.addLayout(bottom)
        self.refresh()

    def refresh(self):
        self.checks = env.run_checks(self.work)
        self.table.setRowCount(len(self.checks))
        for i, c in enumerate(self.checks):
            status = QTableWidgetItem(STATUS_TEXT[c.status])
            status.setForeground(QColor(STATUS_COLOR[c.status]))
            for j, item in enumerate((QTableWidgetItem(c.title), status, QTableWidgetItem(c.detail))):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, item)
            if c.fix:
                b = QPushButton(c.fix_label)
                b.clicked.connect(lambda _=False, action=c.fix: self.fix(action))
                self.table.setCellWidget(i, 3, b)
            else:
                self.table.removeCellWidget(i, 3)
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(1)
        self.table.resizeRowsToContents()

    def fix(self, action):
        try:
            msg = env.apply_fix(action, self.work)
        except Exception as ex:
            QMessageBox.warning(self, "OriginHub", str(ex))
        else:
            QMessageBox.information(self, "OriginHub", msg)
        self.refresh()

    def problems(self) -> int:
        return sum(c.status != "ok" for c in self.checks)
