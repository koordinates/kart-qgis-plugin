import os

from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtWidgets import QProgressBar, QLabel
from qgis.core import QgsProject, Qgis
from qgis.utils import iface

from contextlib import contextmanager


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
        print(value)
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


def layerFromSource(path):
    path = os.path.abspath(path)
    for layer in QgsProject.instance().mapLayers().values():
        if os.path.abspath(layer.source()) == path:
            return layer
