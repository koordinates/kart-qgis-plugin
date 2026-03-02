import os

from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy, QFileDialog

from kart.utils import setting, setSetting, KARTPATH, HELPERMODE, AUTOCOMMIT, DIFFSTYLES, tr

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "settingsdialog.ui")
)

DIFF_STYLES = ["Standard", "GeoInt"]


class SettingsDialog(BASE, WIDGET):
    def __init__(self):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)

        # Initialize translations for UI elements defined in the .ui file
        self.retranslateUi()

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar)

        self.btnBrowsePath.clicked.connect(lambda: self.browse(self.txtKartPath))

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

        self.comboDiffStyles.addItems(DIFF_STYLES)

        self.setValues()

    def retranslateUi(self):
        """Update translations for UI elements from the .ui file"""
        # Window Title
        self.setWindowTitle(QCoreApplication.translate("Dialog", "Kart Settings"))

        # Kart Executable Section
        self.groupBox.setTitle(QCoreApplication.translate("Dialog", "Kart executable"))
        self.label_2.setText(QCoreApplication.translate("Dialog", "Path to Kart executable"))
        self.txtKartPath.setPlaceholderText(
            QCoreApplication.translate("Dialog", "[Leave empty to use default Kart installation path]")
        )
        self.chkHelperMode.setText(QCoreApplication.translate("Dialog", "Use helper mode"))

        # Auto Commit Section
        self.groupBox_3.setTitle(QCoreApplication.translate("Dialog", "Auto commit"))
        self.chkAutoCommit.setText(
            QCoreApplication.translate("Dialog", "Commit automatically after closing editing")
        )

        # Diff Styles Section
        self.groupBox_2.setTitle(QCoreApplication.translate("Dialog", "Diff styles"))
        self.label.setText(QCoreApplication.translate("Dialog", "Styles to use for geometry diffs"))

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
