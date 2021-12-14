import configparser
import os

from qgis.core import QgsProject, Qgis, QgsMessageOutput

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

from kart.gui.dockwidget import KartDockWidget
from kart.gui.settingsdialog import SettingsDialog
from kart.kartapi import checkKartInstalled, kartVersionDetails
from kart.layers import LayerTracker

pluginPath = os.path.dirname(__file__)


def icon(f):
    return QIcon(os.path.join(pluginPath, "img", f))


kartIcon = icon("kart.png")
settingsIcon = icon("settings.png")
aboutIcon = icon("info.png")


class KartPlugin(object):
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):

        self.dock = KartDockWidget()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self.explorerAction = QAction(
            kartIcon, "Kart explorer...", self.iface.mainWindow()
        )
        self.iface.addPluginToMenu("Kart", self.explorerAction)
        self.explorerAction.triggered.connect(self.showDock)
        self.dock.hide()

        self.settingsAction = QAction(
            settingsIcon, "Kart settings...", self.iface.mainWindow()
        )
        self.iface.addPluginToMenu("Kart", self.settingsAction)
        self.settingsAction.triggered.connect(self.openSettings)

        self.aboutAction = QAction(aboutIcon, "About kart...", self.iface.mainWindow())
        self.iface.addPluginToMenu("Kart", self.aboutAction)
        self.aboutAction.triggered.connect(self.openAbout)

        self.tracker = LayerTracker.instance()
        QgsProject.instance().layerWillBeRemoved.connect(self.tracker.layerRemoved)
        QgsProject.instance().layerWasAdded.connect(self.tracker.layerAdded)
        QgsProject.instance().crsChanged.connect(self.tracker.updateRubberBands)

    def showDock(self):
        if checkKartInstalled():
            self.dock.show()

    def openSettings(self):
        dlg = SettingsDialog()
        dlg.exec()

    def pluginVersion(add_commit=False):
        config = configparser.ConfigParser()
        path = os.path.join(os.path.dirname(__file__), "metadata.txt")
        config.read(path)
        version = config.get("general", "version")
        return version

    def openAbout(self):
        pluginVersion = self.pluginVersion()
        kartVersion = kartVersionDetails().replace("\n", "<br>")
        qgisVersion = Qgis.QGIS_VERSION
        html = (
            "<html><style>body, "
            "table {padding:0px; margin:0px; font-family:verdana; font-size: 1.1em;}"
            "</style><body>"
            '<table cellspacing="4" width="100%"><tr><td>'
            f"<h3>QGIS version</h3> <p>{qgisVersion}</p>"
            f"<h3>Kart version details</h3> <p>{kartVersion}</p>"
            f"<h3>Plugin version</h3> <p>{pluginVersion}</p>"
            "</td></tr></table>"
            "</body>"
            "</html>"
        )
        print(html)
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

        QgsProject.instance().layerWillBeRemoved.disconnect(self.tracker.layerRemoved)
        QgsProject.instance().layerWasAdded.disconnect(self.tracker.layerAdded)
