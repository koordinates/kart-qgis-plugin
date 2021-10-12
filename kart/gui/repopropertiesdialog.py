import os

from qgis.core import Qgis
from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy


from kart.kartapi import executeskart
from kart.gui.extentselectionpanel import ExtentSelectionPanel


WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "repopropertiesdialog.ui")
)


class RepoPropertiesDialog(BASE, WIDGET):
    def __init__(self, repo):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)

        self.repo = repo

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar)

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

        self.extentPanel = ExtentSelectionPanel(self)
        self.grpFilter.layout().addWidget(self.extentPanel, 1, 0)

        self.populate()

    @executeskart
    def populate(self):
        self.txtTitle.setText(self.repo.title())
        self.labelLocation.setText(os.path.normpath(self.repo.path))
        spatialFilter = self.repo.spatialFilter()
        if spatialFilter is not None:
            self.grpFilter.setChecked(True)
            self.extentPanel.setValueFromRect(spatialFilter)
        else:
            self.grpFilter.setChecked(False)

    @executeskart
    def okClicked(self):
        self.repo.setTitle(self.txtTitle.text())
        if self.grpFilter.isChecked():
            extent = self.extentPanel.getExtent()
            if extent is None:
                self.bar.pushMessage("Invalid extent value", Qgis.Warning, duration=5)
                return
        else:
            extent = None
        self.repo.setSpatialFilter(extent)
        self.accept()
