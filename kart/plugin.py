import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction

from kart.gui.dockwidget import KartDockWidget
from kart.gui.settingsdialog import SettingsDialog

pluginPath = os.path.dirname(__file__)


class KartPlugin(object):
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):

        self.dock = KartDockWidget()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self.explorerAction = QAction('Kart explorer', self.iface.mainWindow())
        self.iface.addPluginToMenu('Kart', self.explorerAction)
        self.explorerAction.triggered.connect(self.dock.show)
        self.dock.hide()

        self.settingsAction = QAction('Kart settings', self.iface.mainWindow())
        self.iface.addPluginToMenu('Kart', self.settingsAction)
        self.settingsAction.triggered.connect(self.openSettings)

    def openSettings(self):
        dlg = SettingsDialog()
        dlg.exec()


    def unload(self):
        self.iface.removeDockWidget(self.dock)
        self.dock = None
        self.iface.removePluginMenu('Kart', self.action)
