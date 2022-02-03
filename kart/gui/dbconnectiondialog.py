import os

from qgis.utils import iface

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsAuthMethodConfig,
)

from qgis.gui import QgsAuthSettingsWidget, QgsMessageBar

from kart.kartapi import Repository
from kart.utils import waitcursor

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "dbconnectiondialog.ui")
)


class DbConnectionDialog(BASE, WIDGET):
    def __init__(self, parent=None):
        parent = parent or iface.mainWindow()
        super(QDialog, self).__init__(parent)
        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar, 10, 0, 1, 3)

        self.authWidget = QgsAuthSettingsWidget()
        self.layout().addWidget(self.authWidget, 7, 1, 1, 2)

        self.btnLoadTables.clicked.connect(self.loadTables)
        self.buttonBox.accepted.connect(self.okClicked)

        formats = Repository.supportedDbTypes()
        for name, protocol in formats.items():
            self.comboDbType.addItem(name, protocol)

        self.resetTables()

        self.comboDbType.currentIndexChanged.connect(self.resetTables)
        self.txtHost.textChanged.connect(self.resetTables)
        self.txtPort.textChanged.connect(self.resetTables)
        self.txtSchema.textChanged.connect(self.resetTables)
        self.txtDatabase.textChanged.connect(self.resetTables)

    def resetTables(self):
        self.comboTable.clear()
        self.comboTable.addItem("All tables", None)

    def loadTables(self):
        self.resetTables()
        url = self._getUrl()
        try:
            tables = self._getTables(url)
        except Exception:
            self.bar.pushMessage(
                "Cannot connect to the provided database table(s)",
                Qgis.Warning,
                duration=5,
            )
            return
        for table in tables:
            table = table.replace(".", "/")
            self.comboTable.addItem(table, table)
        self.bar.pushMessage(
            "Tables correctly loaded into tables list", Qgis.Success, duration=5
        )

    def okClicked(self):
        url = self._getUrl()
        try:
            self._getTables(url)
        except Exception:
            self.bar.pushMessage(
                "Cannot connect to the provided database table(s)",
                Qgis.Warning,
                duration=5,
            )
            return
        table = self.comboTable.currentData()
        if table is not None:
            url = f"{url}/{table}"
        self.url = url
        self.accept()

    @waitcursor
    def _getTables(self, url):
        return Repository.tablesToImport(url)

    def _getUrl(self):
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

        dbtype = self.comboDbType.currentData()
        host = self.txtHost.text()
        port = self.txtPort.text()
        schema = self.txtSchema.text()
        schema = f"/{schema}" if schema else ""
        database = self.txtDatabase.text()
        if username is not None:
            credentials = f"{username}:{password}@"
        else:
            credentials = ""
        return f"{dbtype}{credentials}{host}:{port}/{database}{schema}"
