import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget

from kart.utils import tr

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "locationselectionpanel.ui"))


class InvalidLocationException(Exception):
    pass


class LocationSelectionPanel(BASE, WIDGET):
    def __init__(self):
        super(QWidget, self).__init__()
        self.setupUi(self)

        self.retranslateUi()

        self.grpPostgis.setVisible(False)
        self.comboStorageType.currentIndexChanged.connect(self.comboChanged)

    def comboChanged(self, idx):
        self.grpPostgis.setVisible(idx != 0)

    def location(self):
        if self.comboStorageType.currentIndex() == 0:
            return None
        else:
            host = self.txtHost.text().strip()
            port = self.txtPort.text().strip()
            database = self.txtDatabase.text().strip()
            schema = self.txtSchema.text().strip()
            if "" in [host, port, database, schema]:
                raise InvalidLocationException
            return f"postgresql://{host}:{port}/{database}/{schema}"

    def retranslateUi(self, *args):
        """Update translations for UI elements from the .ui file"""
        super().retranslateUi(self)

        self.setWindowTitle(tr("Location Selection"))
        self.label.setText(tr("Storage type"))
        self.comboStorageType.setItemText(0, tr("Geopackage in repository folder"))
        self.comboStorageType.setItemText(1, tr("PostGIS database"))
        self.grpPostgis.setTitle(tr("PostGIS parameters"))
        self.label_2.setText(tr("Host"))
        self.label_3.setText(tr("Port"))
        self.label_4.setText(tr("Database"))
        self.label_5.setText(tr("Schema"))
