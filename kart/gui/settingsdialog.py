import os

from qgis.core import Qgis
from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy, QFileDialog

from kart.utils import setting, setSetting, KARTPATH, AUTOCOMMIT, DIFFSTYLES

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "settingsdialog.ui")
)

DIFF_STYLES = ["Standard", "GeoInt"]


class SettingsDialog(BASE, WIDGET):
    def __init__(self):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar)

        self.btnBrowsePath.clicked.connect(lambda: self.browse(self.txtKartPath))

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

        self.comboDiffStyles.addItems(DIFF_STYLES)

        self.setValues()

    def setValues(self):
        self.comboDiffStyles.setCurrentText(setting(DIFFSTYLES))
        self.chkAutoCommit.setChecked(setting(AUTOCOMMIT))
        self.txtKartPath.setText(setting(KARTPATH))

    def browse(self, textbox):
        folder = QFileDialog.getExistingDirectory(
            iface.mainWindow(), "Select Folder", ""
        )
        if folder:
            textbox.setText(folder)

    def okClicked(self):
        setSetting(KARTPATH, self.txtKartPath.text())
        setSetting(AUTOCOMMIT, self.chkAutoCommit.isChecked())
        setSetting(DIFFSTYLES, self.comboDiffStyles.currentText())
        self.accept()
