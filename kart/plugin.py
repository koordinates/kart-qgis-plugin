import configparser
import os
import platform

from qgis.core import QgsApplication, QgsProject, Qgis, QgsMessageOutput

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction

from kart.gui.dockwidget import KartDockWidget
from kart.gui.settingsdialog import SettingsDialog
from kart.kartapi import checkKartInstalled, kartVersionDetails
from kart.layers import LayerTracker
from kart.processing import KartProvider


pluginPath = os.path.dirname(__file__)


class KartPlugin(object):
    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initProcessing(self):
        self.provider = KartProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):

        self.dock = KartDockWidget()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self.explorerAction = QAction("Repositories...", self.iface.mainWindow())
        self.iface.addPluginToMenu("Kart", self.explorerAction)
        self.explorerAction.triggered.connect(self.showDock)
        self.dock.hide()

        self.settingsAction = QAction("Settings...", self.iface.mainWindow())
        self.iface.addPluginToMenu("Kart", self.settingsAction)
        self.settingsAction.triggered.connect(self.openSettings)

        self.aboutAction = QAction("About...", self.iface.mainWindow())
        self.iface.addPluginToMenu("Kart", self.aboutAction)
        self.aboutAction.triggered.connect(self.openAbout)

        self.tracker = LayerTracker.instance()
        QgsProject.instance().layerRemoved.connect(self.tracker.layerRemoved)
        QgsProject.instance().layerWasAdded.connect(self.tracker.layerAdded)
        QgsProject.instance().crsChanged.connect(self.tracker.updateRubberBands)

        self.initProcessing()

    def showDock(self):
        if checkKartInstalled():
            self.dock.show()

    def openSettings(self):
        dlg = SettingsDialog()
        dlg.exec()

    def pluginVersion(add_commit=False):
        config = configparser.ConfigParser()
        path = os.path.join(os.path.dirname(__file__), "metadata.txt")
        config.read(path, encoding="utf-8")
        version = config.get("general", "version")
        return version

    def openAbout(self):
        osInfo = platform.platform().replace("-", " ")
        pluginVersion = self.pluginVersion()
        kartVersion = kartVersionDetails().replace("\n", "<br>")
        qgisVersion = Qgis.QGIS_VERSION
        html = (
            "<html><style>body {padding:0px; margin:0px; font-family:verdana; font-size: 1.1em;}"
            "</style><body>"
            f"<h4>Kart Plugin version</h4><p>{pluginVersion}</p>"
            f"<h4>QGIS version</h4> <p>{qgisVersion}</p>"
            f"<h4>Operating system</h4><p>{osInfo}</p>"
            f"<h4>Kart version</h4> <p>{kartVersion}</p>"
            "</body>"
            "</html>"
        )
        dlg = QgsMessageOutput.createMessageOutput()
        dlg.setTitle("About Kart")
        dlg.setMessage(html, QgsMessageOutput.MessageHtml)
        dlg.showMessage()

    def unload(self):
        self.iface.removeDockWidget(self.dock)
        self.dock = None
        self.iface.removePluginMenu("Kart", self.explorerAction)
        self.iface.removePluginMenu("Kart", self.settingsAction)
        self.iface.removePluginMenu("Kart", self.aboutAction)

        QgsProject.instance().layerRemoved.disconnect(self.tracker.layerRemoved)
        QgsProject.instance().layerWasAdded.disconnect(self.tracker.layerAdded)

        QgsApplication.processingRegistry().removeProvider(self.provider)
