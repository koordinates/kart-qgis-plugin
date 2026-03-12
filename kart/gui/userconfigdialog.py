import os

from qgis.core import Qgis
from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy

from kart.utils import tr


pluginPath = os.path.split(os.path.dirname(__file__))[0]

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "userconfigdialog.ui")
)


class UserConfigDialog(BASE, WIDGET):
    def __init__(self, existingConfigDict):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)

        # Initialize translations for UI elements defined in the .ui file
        self.retranslateUi()

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.layout().addWidget(self.bar)

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)
        self.txtUsername.setText(existingConfigDict.get("user.name"))
        self.txtEmail.setText(existingConfigDict.get("user.email"))

    def okClicked(self):
        self.username = self.txtUsername.text().strip()
        self.email = self.txtEmail.text().strip()
        if self.username and self.email:
            self.accept()
        else:
            self.bar.pushMessage(
                "",
                tr("Username and email must not be empty"),
                Qgis.MessageLevel.Warning,
                duration=5,
            )

    def retranslateUi(self, *args):
        """Update translations for UI elements from the .ui file"""
        self.setWindowTitle(tr("User Configuration"))
