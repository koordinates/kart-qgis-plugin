import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget


WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "locationselectionpanel.ui")
)


class InvalidLocationException(Exception):
    pass


class LocationSelectionPanel(BASE, WIDGET):
    def __init__(self):
        super(QWidget, self).__init__()
        self.setupUi(self)

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
