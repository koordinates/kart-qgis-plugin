import os

from qgis.utils import iface

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog


WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "mergedialog.ui"))


class MergeDialog(BASE, WIDGET):
    def __init__(self, repo):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)

        self.comboTag.addItems(repo.tags())
        self.comboBranch.addItems(repo.branches())

        self.radioBranch.toggled.connect(self.buttonToggled)
        self.radioTag.toggled.connect(self.buttonToggled)

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

        self.buttonToggled()

    def buttonToggled(self):
        self.comboTag.setEnabled(self.radioTag.isChecked())
        self.comboBranch.setEnabled(self.radioBranch.isChecked())

    def okClicked(self):
        if self.radioTag.isChecked():
            self.ref = self.comboTag.currentText()
        else:
            self.ref = self.comboBranch.currentText()
        self.noff = self.chkNoFastForward.isChecked()
        self.ffonly = self.chkFastForwardOnly.isChecked()
        self.message = self.txtMessage.toPlainText().strip()
        self.accept()
