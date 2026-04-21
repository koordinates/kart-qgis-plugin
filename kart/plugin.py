import configparser
import os
import platform

from qgis.core import Qgis, QgsApplication, QgsMessageOutput, QgsProject
from qgis.PyQt.QtCore import QCoreApplication, QSettings, Qt, QTranslator
from qgis.PyQt.QtWidgets import QAction

from kart.gui.dockwidget import KartDockWidget
from kart.gui.icons import kartIcon
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
        self.dock = None
        self.sideDockWidgetArea = Qt.DockWidgetArea.RightDockWidgetArea

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
        # Toolbar
        self.toolbar = self.iface.addToolBar(tr("Kart ToolBar"))
        self.toolbar.setObjectName("KartToolBar")

        self.explorerAction = QAction(kartIcon, tr("Repositories"), self.iface.mainWindow())
        self.explorerAction.setToolTip(tr("Kart Repositories"))
        self.explorerAction.setCheckable(True)
        self.toolbar.addAction(self.explorerAction)

        # Menu
        self.iface.addPluginToMenu("Kart", self.explorerAction)
        self.settingsAction = QAction(tr("Settings"), self.iface.mainWindow())
        self.iface.addPluginToMenu("Kart", self.settingsAction)
        self.settingsAction.triggered.connect(self.openSettings)

        self.aboutAction = QAction(tr("About"), self.iface.mainWindow())
        self.iface.addPluginToMenu("Kart", self.aboutAction)
        self.aboutAction.triggered.connect(self.openAbout)

        # Dock created at startup, hidden
        self.createDockWidget()
        self.dock.hide()

        # Displays a warning to the user if Kart is not installed
        checkKartInstalled()

        self.tracker = LayerTracker.instance()
        QgsProject.instance().layerRemoved.connect(self.tracker.layerRemoved)
        QgsProject.instance().layerWasAdded.connect(self.tracker.layerAdded)
        QgsProject.instance().crsChanged.connect(self.tracker.updateRubberBands)

        self.initProcessing()

    def createDockWidget(self):
        """Creates and registers the Kart dock widget."""
        self.dock = KartDockWidget()
        self.dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.dock.setFloating(False)
        self.iface.addDockWidget(self.sideDockWidgetArea, self.dock)
        self.iface.addTabifiedDockWidget(self.sideDockWidgetArea, self.dock, [], True)

        # setToggleVisibilityAction automatically manages the show/hide and state of the button
        self.dock.setToggleVisibilityAction(self.explorerAction)
        self.dock.dockLocationChanged.connect(self.onDockLocationChanged)

    def onDockLocationChanged(self, area):
        """Tracks the dock widget's current location to restore it on recreation."""
        self.sideDockWidgetArea = area

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
        if self.dock is not None:
            self.dock.dockLocationChanged.disconnect(self.onDockLocationChanged)
            self.iface.removeDockWidget(self.dock)
            self.dock = None
        self.iface.removePluginMenu("Kart", self.explorerAction)
        self.iface.removePluginMenu("Kart", self.settingsAction)
        self.iface.removePluginMenu("Kart", self.aboutAction)
        del self.toolbar

        QgsProject.instance().layerRemoved.disconnect(self.tracker.layerRemoved)
        QgsProject.instance().layerWasAdded.disconnect(self.tracker.layerAdded)
        QgsProject.instance().crsChanged.disconnect(self.tracker.updateRubberBands)

        QgsApplication.processingRegistry().removeProvider(self.provider)

        if self.translator:
            QCoreApplication.removeTranslator(self.translator)