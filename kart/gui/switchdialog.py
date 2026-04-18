import os

from qgis.utils import iface
from qgis.PyQt import uic
#from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QInputDialog

from kart.kartapi import executeskart
from kart.utils import tr


WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "switchdialog.ui")
)


class SwitchDialog(BASE, WIDGET):
    def __init__(self, repo):
        super().__init__(iface.mainWindow())
        self.repo = repo
        self.setupUi(self)
        
        # Initialize translations for UI elements defined in the .ui file
        self.retranslateUi()

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
            self, tr("Create branch"), tr("Enter name of branch to create")
        )
        if ok and name:
            self.repo.createBranch(name)
            self.branch = name
            self.force = False
            self.accept()

    def retranslateUi(self, *args):
        """Update translations for UI elements from the .ui file"""
        super().retranslateUi(self)

        # Window Title
        self.setWindowTitle(tr("Switch/Checkout"))

        # GroupBox "Switch to"
        self.groupBox.setTitle(tr("Switch to"))
        self.label.setText(tr("Branch"))
        #self.btnCreateNew.setText(tr("Create New"))

        # GroupBox "Options"
        self.grpOptions.setTitle(tr("Options"))
        self.chkForce.setText(tr("Overwrite working copy changes (force)"))