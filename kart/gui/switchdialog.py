import os

from qgis.utils import iface
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QInputDialog

from kart.kartapi import executeskart


WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "switchdialog.ui")
)


class SwitchDialog(BASE, WIDGET):
    def __init__(self, repo):
        super().__init__(iface.mainWindow())
        self.repo = repo
        self.setupUi(self)

        self.comboBranch.addItems(repo.branches())

        self.btnCreateNew.clicked.connect(self.createNewClicked)

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

    def okClicked(self):
        self.branch = self.comboBranch.currentText()
        self.force = self.chkForce.isChecked()
        self.accept()

    @executeskart
    def createNewClicked(self, item):
        name, ok = QInputDialog.getText(
            self, "Create branch", "Enter name of branch to create"
        )
        if ok and name:
            self.repo.createBranch(name)
            self.branch = name
            self.force = False
            self.accept()
