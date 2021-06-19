
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction

from kart.gui.dockwidget import KartDockWidget

pluginPath = os.path.dirname(__file__)


class KartPlugin(object):

    def __init__(self, iface):
        self.iface = iface

    def initGui(self):

        self.dock = KartDockWidget()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self.action = QAction('Kart explorer',
                              self.iface.mainWindow())
        self.iface.addPluginToMenu('Kart', self.action)
        self.action.triggered.connect(self.dock.show)
        self.dock.hide()


    def unload(self):
        self.iface.removeDockWidget(self.dock)
        self.dock = None
        self.iface.removePluginMenu('Kart', self.action)
