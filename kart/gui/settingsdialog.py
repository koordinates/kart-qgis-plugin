import os

from qgis.gui import QgsMessageBar
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QFileDialog, QSizePolicy
from qgis.utils import iface

from kart.utils import (
    AUTOCOMMIT,
    CURRENT_COLOR_ADDED,
    CURRENT_COLOR_MODIFIED,
    CURRENT_COLOR_REMOVED,
    CURRENT_COLOR_UNCHANGED,
    DIFFSTYLES,
    HELPERMODE,
    KARTPATH,
    PALETTES,
    setSetting,
    setting,
    tr,
)

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "settingsdialog.ui"))


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

        # Fill combo from the central dictionary
        self.comboDiffStyles.clear()
        self.comboDiffStyles.addItems(PALETTES.keys())

        self.setValues()

    def setValues(self):
        current_style = setting(DIFFSTYLES) or "Standard"
        if current_style in PALETTES:
            self.comboDiffStyles.setCurrentText(current_style)

        self.chkHelperMode.setChecked(setting(HELPERMODE))
        self.chkAutoCommit.setChecked(setting(AUTOCOMMIT))
        self.txtKartPath.setText(setting(KARTPATH))

    def browse(self, textbox):
        folder = QFileDialog.getExistingDirectory(iface.mainWindow(), tr("Select Folder"), "")
        if folder:
            textbox.setText(folder)

    def okClicked(self):
        selected_style = self.comboDiffStyles.currentText()

        setSetting(KARTPATH, self.txtKartPath.text())
        setSetting(HELPERMODE, self.chkHelperMode.isChecked())
        setSetting(AUTOCOMMIT, self.chkAutoCommit.isChecked())
        setSetting(DIFFSTYLES, selected_style)

        # Deploy colors from selected palette to current settings
        if selected_style in PALETTES:
            palette = PALETTES[selected_style]
            setSetting(CURRENT_COLOR_ADDED, palette["ADDED"])
            setSetting(CURRENT_COLOR_REMOVED, palette["REMOVED"])
            setSetting(CURRENT_COLOR_MODIFIED, palette["MODIFIED"])
            setSetting(CURRENT_COLOR_UNCHANGED, palette["UNCHANGED"])

        self.accept()

    def retranslateUi(self, *args):
        """Update translations for UI elements from the .ui file"""
        super().retranslateUi(self)

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
