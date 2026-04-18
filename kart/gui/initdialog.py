import os

from qgis.core import Qgis
from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy, QFileDialog

from kart.gui.locationselectionpanel import (
    LocationSelectionPanel,
    InvalidLocationException,
)

from kart.utils import tr

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "initdialog.ui"))


class InitDialog(BASE, WIDGET):
    def __init__(self):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)

        self.retranslateUi()

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.layout().addWidget(self.bar)

        self.btnBrowse.clicked.connect(self.browse)

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

        self.locationPanel = LocationSelectionPanel()
        self.grpLocation.layout().addWidget(self.locationPanel, 1, 0)

    def browse(self):
        folder = QFileDialog.getExistingDirectory(
            iface.mainWindow(), tr("Select Folder"), ""
        )
        if folder:
            self.txtFolder.setText(folder)

    def okClicked(self):
        try:
            self.location = self.locationPanel.location()
        except InvalidLocationException:
            self.bar.pushMessage(
                tr("Invalid location definition"), Qgis.MessageLevel.Warning, duration=5
            )
            return
        self.folder = self.txtFolder.text()
        if self.folder:
            self.accept()
        else:
            self.bar.pushMessage(
                tr("Text fields must not be empty"),
                Qgis.MessageLevel.Warning,
                duration=5,
            )

    def retranslateUi(self, *args):
        """Update translations for UI elements from the .ui file"""
        super().retranslateUi(self)

        self.setWindowTitle(tr("New Repository"))
        self.groupBox.setTitle(tr("Repository location"))
        self.label_2.setText(tr("Repository folder"))
        self.grpLocation.setTitle(tr("Working copy location"))
