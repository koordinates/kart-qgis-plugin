import os

from qgis.core import Qgis
from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QDialog,
    QSizePolicy
)

from kart.kartapi import executeskart

pluginPath = os.path.split(os.path.dirname(__file__))[0]

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "remotesdialog.ui")
)


class RemotesDialog(BASE, WIDGET):
    def __init__(self, repo):
        super(QDialog, self).__init__(iface.mainWindow())
        self.repo = repo
        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar)

        self.listWidget.itemClicked.connect(self.itemClicked)
        self.btnAdd.clicked.connect(self.addRemote)
        self.btnRemove.clicked.connect(self.removeRemote)

        self.buttonBox.accepted.connect(self.accept)

        self.fillContent()

    @executeskart
    def fillContent(self):
        self.remotes = self.repo.remotes()
        self.listWidget.addItems(self.remotes.keys())

    def itemClicked(self, item):
        self.txtName.setText(item.text())
        self.txtUrl.setText(self.remotes[item.text()])

    def addRemote(self):
        name = self.txtName.text()
        url = self.txtUrl.text()
        if not name or not url:
            self.bar.pushMessage("", "Values for both remote name and url must be provided", Qgis.Warning, duration=5)
            return

    @executeskart
    def _addRemote(self, name, url):
        if name in self.remotes:
            self.repo.removeRemote(name)
            self.repo.addRemote(name, url)
        else:
            self.repo.addRemote(name, url)
            self.listWidget.addItem(name)
        self.remotes[name] = url

    def removeRemote(self):
        name = self.txtName.text()
        item = self.itemFromName(name)
        if item is None:
            self.bar.pushMessage("", "A remote with that name does not exist", Qgis.Warning, duration=5)
        else:
            self._removeRemote(name)
            self.listWidget.takeItem(item)

    @executeskart
    def _removeRemote(self, name):
        self.repo.removeRemote(name)

    def itemFromName(self, name):
        for i in range(self.listWidget.count()):
            item = self.listWidget(i)
            if item.text() == name:
                return item