import os
from contextlib import contextmanager

from qgis.core import Qgis, QgsProject
from qgis.PyQt.QtCore import (
    QCoreApplication,
    QSettings,
    Qt,
)
from qgis.PyQt.QtWidgets import QApplication, QLabel, QMessageBox, QProgressBar
from qgis.utils import iface as qgisiface

# This can be further patched using the test.utils module
iface = qgisiface
if iface is None:
    from qgis.testing.mocked import get_iface

    iface = get_iface()


def tr(string):
    # Does the function not return the context?
    # return QCoreApplication.translate("Kart", string)
    # Using @default as a fallback
    return QCoreApplication.translate("@default", string)


class ProgressBar:
    def __init__(self, title):
        self.progressMessageBar = iface.messageBar().createMessage(f"<b>{title}</b>")
        self.label = QLabel()
        self.progressMessageBar.layout().addWidget(self.label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.progressMessageBar.layout().addWidget(self.progress)
        iface.messageBar().pushWidget(self.progressMessageBar, Qgis.MessageLevel.Info)
        QCoreApplication.processEvents()

    def setValue(self, value):
        self.progress.setValue(value)
        QCoreApplication.processEvents()

    def setText(self, text):
        self.label.setText(text)
        QCoreApplication.processEvents()

    def close(self):
        iface.messageBar().popWidget(self.progressMessageBar)


@contextmanager
def progressBar(title):
    iface.messageBar().clearWidgets()
    bar = ProgressBar(title)
    try:
        yield bar
    finally:
        bar.close()


def waitcursor(method):
    def func(*args, **kw):
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            return method(*args, **kw)
        except Exception as ex:
            raise ex
        finally:
            QApplication.restoreOverrideCursor()

    return func


def confirm(msg):
    ret = QMessageBox.warning(
        iface.mainWindow(),
        "Kart",
        msg,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return ret == QMessageBox.StandardButton.Yes


def layerFromSource(path):
    path = os.path.abspath(path)
    for layer in QgsProject.instance().mapLayers().values():
        if os.path.abspath(layer.source()) == path:
            return layer


NAMESPACE = "kart"
KARTPATH = "KartPath"
HELPERMODE = "HelperMode"
AUTOCOMMIT = "AutoCommit"
DIFFSTYLES = "DiffStyles"
LASTREPO = "LastRepo"

# Palette Definitions
PALETTES = {
    "Standard": {
        "ADDED": "#54c35f",  # QColor(84, 195, 95)
        "REMOVED": "#e8718d",  # QColor(232, 113, 141)
        "MODIFIED": "#ffbe64",  # QColor(255, 190, 100)
        "UNCHANGED": "#ffffff",  # QColor(255, 255, 255)
    },
    "GeoInt": {
        "ADDED": "#1e90ff",  # QColor(30, 144, 255)
        "REMOVED": "#ff4500",  # QColor(255, 69, 0)
        "MODIFIED": "#ffbe64",  # QColor(255, 190, 100)
        "UNCHANGED": "#ffffff",  # QColor(255, 255, 255)
    },
}

# Current active colors
CURRENT_COLOR_ADDED = "CurrentColorAdded"
CURRENT_COLOR_REMOVED = "CurrentColorRemoved"
CURRENT_COLOR_MODIFIED = "CurrentColorModified"
CURRENT_COLOR_UNCHANGED = "CurrentColorUnchanged"

setting_types = {HELPERMODE: bool, AUTOCOMMIT: bool}


def setSetting(name, value):
    QSettings().setValue(f"{NAMESPACE}/{name}", value)


def setting(name):
    v = QSettings().value(f"{NAMESPACE}/{name}", None)
    if setting_types.get(name, str) is bool:
        return str(v).lower() == str(True).lower()
    else:
        return v
