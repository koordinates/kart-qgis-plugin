import os
from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy, QFileDialog

from kart.utils import (
    setting,
    setSetting,
    KARTPATH,
    HELPERMODE,
    AUTOCOMMIT,
    DIFFSTYLES,
    tr,
)

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "settingsdialog.ui")
)

DIFF_STYLES = ["Standard", "GeoInt"]


class SettingsDialog(BASE, WIDGET):
    def __init__(self):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)

        self.retranslateUi()

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.layout().addWidget(self.bar)

        self.btnBrowsePath.clicked.connect(lambda: self.browse(self.txtKartPath))

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

        self.comboDiffStyles.addItems(DIFF_STYLES)

        self.setValues()

    def setValues(self):
        self.comboDiffStyles.setCurrentText(setting(DIFFSTYLES))
        self.chkHelperMode.setChecked(setting(HELPERMODE))
        self.chkAutoCommit.setChecked(setting(AUTOCOMMIT))
        self.txtKartPath.setText(setting(KARTPATH))

    def browse(self, textbox):
        folder = QFileDialog.getExistingDirectory(
            iface.mainWindow(), tr("Select Folder"), ""
        )
        if folder:
            textbox.setText(folder)

    def okClicked(self):
        setSetting(KARTPATH, self.txtKartPath.text())
        setSetting(HELPERMODE, self.chkHelperMode.isChecked())
        setSetting(AUTOCOMMIT, self.chkAutoCommit.isChecked())
        setSetting(DIFFSTYLES, self.comboDiffStyles.currentText())
        self.accept()

    def retranslateUi(self, *args):
        """Update translations for UI elements from the .ui file"""
        # Window Title
        self.setWindowTitle(tr("Kart Settings"))

        # Kart Executable Section
        self.groupBox.setTitle(tr("Kart executable"))
        self.label_2.setText(tr("Path to Kart executable"))
        self.txtKartPath.setPlaceholderText(
            tr("[Leave empty to use default Kart installation path]")
        )
        self.chkHelperMode.setText(tr("Use helper mode"))

        # Auto Commit Section
        self.groupBox_3.setTitle(tr("Auto commit"))
        self.chkAutoCommit.setText(tr("Commit automatically after closing editing"))

        # Diff Styles Section
        self.groupBox_2.setTitle(tr("Diff styles"))
        self.label.setText(tr("Styles to use for geometry diffs"))
