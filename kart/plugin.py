import os

from qgis.core import Qgis, QgsProject

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction

from kart.gui.dockwidget import KartDockWidget
from kart.gui.settingsdialog import SettingsDialog
from kart.kartapi import isKartInstalled
from kart.layers import LayerTracker

pluginPath = os.path.dirname(__file__)


class KartPlugin(object):
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):

        self.dock = KartDockWidget()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self.explorerAction = QAction("Kart explorer", self.iface.mainWindow())
        self.iface.addPluginToMenu("Kart", self.explorerAction)
        self.explorerAction.triggered.connect(self.showDock)
        self.dock.hide()

        self.settingsAction = QAction("Kart settings", self.iface.mainWindow())
        self.iface.addPluginToMenu("Kart", self.settingsAction)
        self.settingsAction.triggered.connect(self.openSettings)

        self.tracker = LayerTracker.instance()
        QgsProject.instance().layerWillBeRemoved.connect(self.tracker.layerRemoved)
        QgsProject.instance().layerWasAdded.connect(self.tracker.layerAdded)

    def showDock(self):
        if isKartInstalled():
            self.dock.show()
        else:
            self.iface.messageBar().pushMessage(
                "Error",
                "Kart folder is not configured or Kart is not installed in the specified folder",
                level=Qgis.Warning,
            )

    def openSettings(self):
        dlg = SettingsDialog()
        dlg.exec()

    def unload(self):
        self.iface.removeDockWidget(self.dock)
        self.dock = None
        self.iface.removePluginMenu("Kart", self.action)

        QgsProject.instance().layerWillBeRemoved.disconnect(self.tracker.layerRemoved)
        QgsProject.instance().layerWasAdded.disconnect(self.tracker.layerAdded)
