import os

from qgis.PyQt.QtCore import Qt, QCoreApplication, QSettings
from qgis.PyQt.QtWidgets import QProgressBar, QLabel, QMessageBox
from qgis.core import QgsProject, Qgis
from qgis.utils import iface as qgisiface
from qgis.testing.mocked import get_iface

from contextlib import contextmanager


# This can be further patched using the test.utils module
iface = qgisiface
if iface is None:
    iface = get_iface()


class ProgressBar:
    def __init__(self, title):
        self.progressMessageBar = iface.messageBar().createMessage(f"<b>{title}</b>")
        self.label = QLabel()
        self.progressMessageBar.layout().addWidget(self.label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.progressMessageBar.layout().addWidget(self.progress)
        iface.messageBar().pushWidget(self.progressMessageBar, Qgis.Info)
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


def confirm(msg):
    ret = QMessageBox.warning(
        iface.mainWindow(), "Kart", msg, QMessageBox.Yes | QMessageBox.No
    )
    return ret == QMessageBox.Yes


def layerFromSource(path):
    path = os.path.abspath(path)
    for layer in QgsProject.instance().mapLayers().values():
        if os.path.abspath(layer.source()) == path:
            return layer


NAMESPACE = "kart"
KARTPATH = "KartPath"
AUTOCOMMIT = "AutoCommit"
DIFFSTYLES = "DiffStyles"
LASTREPO = "LastRepo"

setting_types = {AUTOCOMMIT: bool}


def setSetting(name, value):
    QSettings().setValue(f"{NAMESPACE}/{name}", value)


def setting(name):
    v = QSettings().value(f"{NAMESPACE}/{name}", None)
    if setting_types.get(name, str) == bool:
        return str(v).lower() == str(True).lower()
    else:
        return v
