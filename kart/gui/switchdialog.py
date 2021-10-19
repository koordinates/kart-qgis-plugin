import os

from qgis.utils import iface

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog


WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "switchdialog.ui")
)


class SwitchDialog(BASE, WIDGET):
    def __init__(self, repo):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)

        self.comboBranch.addItems(repo.branches())

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

    def okClicked(self):
        self.branch = self.comboBranch.currentText()
        self.force = self.chkForce.isChecked()
        self.accept()
