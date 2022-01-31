import os

from qgis.utils import iface

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy
from qgis.core import (
    Qgis,
    QgsVectorLayer,
    QgsApplication,
    QgsAuthMethodConfig,
    QgsDataSourceUri,
)

from qgis.gui import QgsAuthSettingsWidget, QgsMessageBar


WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "postgisconnectiondialog.ui")
)


class PostgisConnectionDialog(BASE, WIDGET):
    def __init__(self, parent=None):
        parent = parent or iface.mainWindow()
        super(QDialog, self).__init__(parent)
        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar, 0, 0, 1, 2)

        self.authWidget = QgsAuthSettingsWidget()
        self.layout().addWidget(self.authWidget, 7, 1)

        self.buttonBox.accepted.connect(self.okClicked)

    def okClicked(self):
        table = self.txtTable.text()
        host = self.txtHost.text()
        port = self.txtPort.text()
        schema = self.txtSchema.text()
        schema = self.txtTable.text()
        database = self.txtDatabase.text()
        if self.authWidget.configurationTabIsSelected():
            authid = self.authWidget.configId()
            if authid:
                authConfig = QgsAuthMethodConfig()
                QgsApplication.authManager().loadAuthenticationConfig(
                    authid, authConfig, True
                )
                username = authConfig.config("username")
                password = authConfig.config("password")
            else:
                username = None
                password = None
        else:
            username = self.authWidget.username()
            password = self.authWidget.password()
        uri = QgsDataSourceUri()
        uri.setConnection(host, port, database, username, password)
        uri.setSchema(schema)
        uri.setTable(table)
        layer = QgsVectorLayer(uri.uri(False), table, "postgres")
        if layer.isValid():
            if username is None:
                self.url = f"postgresql://{host}:{port}/{database}/{schema}"
            else:
                self.url = f"postgresql://{username}:{password}@{host}:{port}/{database}/{schema}"
            self.accept()
        else:
            self.bar.pushMessage(
                "Cannot connect to the provided table", Qgis.Warning, duration=5
            )
