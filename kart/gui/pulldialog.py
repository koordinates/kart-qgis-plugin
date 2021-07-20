import os

from qgis.core import Qgis
from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy

from kart.kartapi import executeskart
from kart.gui.remotesdialog import RemotesDialog

pluginPath = os.path.split(os.path.dirname(__file__))[0]

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "pulldialog.ui"))


class PullDialog(BASE, WIDGET):
    def __init__(self, repo):
        super(QDialog, self).__init__(iface.mainWindow())
        self.repo = repo
        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
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
                "", "Branch and remote must not be empty", Qgis.Warning, duration=5
            )
        else:
            self.accept()
