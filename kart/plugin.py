
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction

from qgis.core import QgsProject

from kart.gui.dockwidget import KartDockWidget

pluginPath = os.path.dirname(__file__)


class LartPlugin(object):

    def __init__(self, iface):
        self.iface = iface

    def initGui(self):

        self.dock = KartDockWidget()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self.action = QAction('Kart explorer',
                              self.iface.mainWindow())
        self.iface.addPluginToMenu('Detektia', self.action)
        self.action.triggered.connect(self.dock.show)
        self.dock.hide()

        QgsProject.instance().layersAdded.connect(self.dock._layersAdded)
        QgsProject.instance().layersRemoved.connect(self.dock._layersRemoved)

    def unload(self):
        self.iface.removeDockWidget(self.dock)
        self.dock = None
        self.iface.removePluginMenu('Detektia', self.action)
