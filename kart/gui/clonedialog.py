import os

from qgis.core import Qgis
from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QSizePolicy, QFileDialog

pluginPath = os.path.split(os.path.dirname(__file__))[0]

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "clonedialog.ui"))


class CloneDialog(BASE, WIDGET):
    def __init__(self):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().addWidget(self.bar)

        self.btnBrowseSrc.clicked.connect(lambda: self.browse(self.txtSrc))
        self.btnBrowseDst.clicked.connect(lambda: self.browse(self.txtDst))

        self.buttonBox.accepted.connect(self.okClicked)
        self.buttonBox.rejected.connect(self.reject)

    def browse(self, textbox):
        folder = QFileDialog.getExistingDirectory(
            iface.mainWindow(), "Select Folder", ""
        )
        if folder:
            textbox.setText(folder)

    def okClicked(self):
        src = self.txtSrc.text()
        dst = self.txtDst.text()
        if src and dst:
            self.result = src, dst
            self.accept()
        else:
            self.bar.pushMessage(
                "Text fields must not be empty", Qgis.Warning, duration=5
            )
