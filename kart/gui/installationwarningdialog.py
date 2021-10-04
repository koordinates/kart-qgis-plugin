import webbrowser

from qgis.PyQt.QtWidgets import (
    QVBoxLayout,
    QDialog,
    QTextBrowser,
    QDialogButtonBox,
)


from qgis.utils import iface

from kart.gui.settingsdialog import SettingsDialog


class InstallationWarningDialog(QDialog):
    def __init__(self, msg):
        super(InstallationWarningDialog, self).__init__(iface.mainWindow())
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout = QVBoxLayout()
        text = QTextBrowser()
        text.setHtml(msg)
        text.setOpenLinks(False)
        text.anchorClicked.connect(self.anchorClicked)
        layout.addWidget(text)
        layout.addWidget(self.buttonBox)
        self.setLayout(layout)
        self.setFixedWidth(500)
        self.setWindowTitle("Kart")

    def anchorClicked(self, url):
        if url.toString() == "settings":
            self.close()
            dlg = SettingsDialog()
            dlg.exec()
        else:
            webbrowser.open_new_tab(url.toString())