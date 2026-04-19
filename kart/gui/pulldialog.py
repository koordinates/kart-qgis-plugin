import os

from qgis.core import Qgis
from qgis.gui import QgsMessageBar
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy
from qgis.utils import iface

from kart.gui.remotesdialog import RemotesDialog
from kart.kartapi import executeskart
from kart.utils import tr

pluginPath = os.path.split(os.path.dirname(__file__))[0]

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "pulldialog.ui"))


class PullDialog(BASE, WIDGET):
    def __init__(self, repo):
        super(QDialog, self).__init__(iface.mainWindow())
        self.repo = repo
        self.setupUi(self)

        # Initialize translations for UI elements defined in the .ui file
        self.retranslateUi()

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.layout().addWidget(self.bar)

        self.btnManageRemotes.clicked.connect(self.manageRemotes)

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

        self.fillContent()

    def manageRemotes(self):
        dialog = RemotesDialog(self.repo)
        dialog.exec()
        self.fillContent()

    @executeskart
    def fillContent(self):
        self.comboRemote.clear()
        self.comboBranch.clear()
        remotes = self.repo.remotes().keys()
        self.comboRemote.addItems(remotes)
        branches = self.repo.branches()
        self.comboBranch.addItems(branches)

    def okClicked(self):
        self.branch = self.comboBranch.currentText()
        self.remote = self.comboRemote.currentText()
        if not self.remote:
            self.bar.pushMessage(
                "",
                tr("Branch and remote must not be empty"),
                Qgis.MessageLevel.Warning,
                duration=5,
            )
        else:
            self.accept()

    def retranslateUi(self, *args):
        """Update translations for UI elements from the .ui file"""
        super().retranslateUi(self)

        self.setWindowTitle(tr("Pull"))
        self.groupBox.setTitle(tr("Remote"))
        self.label.setText(tr("Remote:"))
        self.label_2.setText(tr("Remote branch:"))
        self.btnManageRemotes.setText(tr("Manage remotes"))
