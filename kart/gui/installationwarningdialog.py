import os
import sys
import subprocess
import tempfile
import requests
import webbrowser
import shutil

from qgis.PyQt.QtWidgets import QDialog

from qgis.PyQt import uic


from qgis.utils import iface

from kart.gui.settingsdialog import SettingsDialog
from kart.utils import waitcursor

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "installationwarningdialog.ui")
)

DOWNLOAD_URL = "https://github.com/koordinates/kart/releases/download/v{version}"
RELEASE_URL = "https://github.com/koordinates/kart/releases/tag/v{version}"

WINDOWS_FILE = "Kart-{version}.msi"
OSX_FILE = "Kart-{version}.pkg"


class InstallationWarningDialog(BASE, WIDGET):
    def __init__(self, msg, supportedVersion):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)
        self.supportedVersion = supportedVersion
        self.widgetDownload.setVisible(False)
        self.btnInstall.clicked.connect(self.install)
        self.btnOpenSettings.clicked.connect(self.openSettings)
        self.btnClose.clicked.connect(self.close)
        self.textBrowser.setText(msg)

    def _download(self, url, filename):
        self.progressBar.setValue(0)
        self.widgetDownload.setVisible(True)
        fullurl = f"{url}/{filename}"
        dirname = tempfile.mkdtemp()
        fullpath = os.path.join(dirname, filename)
        chunk_size = 1024
        r = requests.get(fullurl, stream=True)
        file_size = r.headers.get("content-length") or 0
        file_size = int(file_size)
        percentage_per_chunk = 100.0 / (file_size / chunk_size)
        progress = 0
        with open(fullpath, "wb") as f:
            for chunk in r.iter_content(chunk_size):
                f.write(chunk)
                progress += percentage_per_chunk
                self.progressBar.setValue(int(progress))
        return fullpath

    def install(self):
        try:
            self._install()
        except Exception:
            pass  # a later check will tell the user that kart could not be installed

    @waitcursor
    def _install(self):
        url = DOWNLOAD_URL.format(version=self.supportedVersion)
        if os.name == "nt":
            filename = WINDOWS_FILE.format(version=self.supportedVersion)
            msipath = self._download(url, filename)
            powershell = os.path.join(
                os.getenv("SystemRoot"),
                r"system32\WindowsPowerShell\v1.0\powershell.exe",
            )
            command = (
                fr"""{powershell} -Command "& {{ Start-Process 'msiexec' -ArgumentList @('/a',"""
                fr''' '{msipath}', '/qb', 'TARGETDIR=\"%ProgramFiles%\"') -Verb RunAs -Wait}}"'''
            )
            subprocess.call(command, shell=True)
            shutil.rmtree(os.path.dirname(msipath))
        elif sys.platform == "darwin":
            filename = OSX_FILE.format(version=self.supportedVersion)
            pkgpath = self._download(url, filename)
            command = f"open -W {pkgpath}"
            subprocess.call(command, shell=True)
            shutil.rmtree(os.path.dirname(pkgpath))
        else:
            url = RELEASE_URL.format(version=self.supportedVersion)
            webbrowser.open_new_tab(url)
        self.accept()

    def openSettings(self):
        self.accept()
        dlg = SettingsDialog()
        dlg.exec()
