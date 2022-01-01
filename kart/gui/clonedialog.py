import os

from qgis.core import Qgis
from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy, QFileDialog

from kart.gui.extentselectionpanel import ExtentSelectionPanel
from kart.gui.locationselectionpanel import (
    LocationSelectionPanel,
    InvalidLocationException,
)

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "clonedialog.ui"))


class CloneDialog(BASE, WIDGET):
    def __init__(self, parent=None):
        parent = parent or iface.mainWindow()
        super(QDialog, self).__init__(parent)
        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar)

        self.btnBrowseSrc.clicked.connect(lambda: self.browse(self.txtSrc))
        self.btnBrowseDst.clicked.connect(lambda: self.browse(self.txtDst))

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

        self.extentPanel = ExtentSelectionPanel(self)
        self.grpFilter.layout().addWidget(self.extentPanel, 1, 0)

        self.locationPanel = LocationSelectionPanel()
        self.grpLocation.layout().addWidget(self.locationPanel, 1, 0)

    def browse(self, textbox):
        folder = QFileDialog.getExistingDirectory(
            iface.mainWindow(), "Select Folder", ""
        )
        if folder:
            textbox.setText(folder)

    def okClicked(self):
        try:
            self.location = self.locationPanel.location()
        except InvalidLocationException:
            self.bar.pushMessage(
                "Invalid location definition", Qgis.Warning, duration=5
            )
            return
        self.src = self.txtSrc.text()
        self.dst = self.txtDst.text()
        if self.grpFilter.isChecked():
            self.extent = self.extentPanel.getExtent()
            if self.extent is None:
                self.bar.pushMessage("Invalid extent value", Qgis.Warning, duration=5)
                return
        else:
            self.extent = None
        if self.src and self.dst:
            self.accept()
        else:
            self.bar.pushMessage(
                "Text fields must not be empty", Qgis.Warning, duration=5
            )
