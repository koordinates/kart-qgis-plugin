import configparser
import os
import platform

from qgis.core import QgsApplication, QgsProject, Qgis, QgsMessageOutput

from qgis.PyQt.QtCore import Qt, QCoreApplication, QSettings, QTranslator
from qgis.PyQt.QtWidgets import QAction

from kart.gui.dockwidget import KartDockWidget
from kart.gui.settingsdialog import SettingsDialog
from kart.kartapi import checkKartInstalled, kartVersionDetails
from kart.layers import LayerTracker
from kart.processing import KartProvider
from kart.utils import tr

pluginPath = os.path.dirname(__file__)


class KartPlugin(object):
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.translator = None

        # Adds support for internationalization
        locale = QSettings().value("locale/userLocale")
        locale_path = os.path.join(pluginPath, "i18n", f"kart_{locale}.qm")
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

    def initProcessing(self):
        self.provider = KartProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):

        self.dock = KartDockWidget()
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

        self.explorerAction = QAction(tr("Repositories..."), self.iface.mainWindow())
        self.iface.addPluginToMenu("Kart", self.explorerAction)
        self.explorerAction.triggered.connect(self.showDock)
        self.dock.hide()

        self.settingsAction = QAction(tr("Settings..."), self.iface.mainWindow())
        self.iface.addPluginToMenu("Kart", self.settingsAction)
        self.settingsAction.triggered.connect(self.openSettings)

        self.aboutAction = QAction(tr("About..."), self.iface.mainWindow())
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

        html_template = (
            "<html><style>"
            "body {{padding:0px; margin:0px; font-family:verdana; font-size: 1.1em;}}"
            "</style><body>"
            "<h4>{label_plugin}</h4><p>{plugin_ver}</p>"
            "<h4>{label_qgis}</h4><p>{qgis_ver}</p>"
            "<h4>{label_os}</h4><p>{os_info}</p>"
            "<h4>{label_kart}</h4><p>{kart_ver}</p>"
            "</body></html>"
        )

        html = html_template.format(
            label_plugin=tr("Kart Plugin version"),
            plugin_ver=pluginVersion,
            label_qgis=tr("QGIS version"),
            qgis_ver=qgisVersion,
            label_os=tr("Operating system"),
            os_info=osInfo,
            label_kart=tr("Kart version"),
            kart_ver=kartVersion,
        )

        dlg = QgsMessageOutput.createMessageOutput()
        dlg.setTitle(tr("About Kart"))
        dlg.setMessage(html, QgsMessageOutput.MessageType.MessageHtml)
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

        if self.translator:
            QCoreApplication.removeTranslator(self.translator)
