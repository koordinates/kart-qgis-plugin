import os
import requests
import shutil
import subprocess
import sys
import tempfile
import webbrowser

from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtCore import QThread, Qt, pyqtSignal, QEventLoop
from qgis.PyQt import uic

from qgis.utils import iface

from kart.gui.settingsdialog import SettingsDialog
from kart import logging

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "installationwarningdialog.ui")
)

DOWNLOAD_URL = "https://github.com/koordinates/kart/releases/download/v{version}"
RELEASE_URL = "https://github.com/koordinates/kart/releases/tag/v{version}"

WINDOWS_FILE = "Kart-{version}-win64.msi"
MACOS_FILE = "Kart-{version}-macOS-{arch}.pkg"


class DownloadAndInstallThread(QThread):

    downloadProgressChanged = pyqtSignal(int)
    downloadFinished = pyqtSignal()
    finished = pyqtSignal()

    def __init__(self, version: str):
        QThread.__init__(self, iface.mainWindow())
        self.version = version

    def run(self):
        try:
            url = DOWNLOAD_URL.format(version=self.version)
            if os.name == "nt":
                filename = WINDOWS_FILE.format(version=self.version)
                msipath = self._download(url, filename)
                powershell = os.path.join(
                    os.getenv("SystemRoot"),
                    r"system32\WindowsPowerShell\v1.0\powershell.exe",
                )
                command = (
                    rf"""{powershell} -Command "& {{ Start-Process 'msiexec' """
                    rf"""-ArgumentList @('/a', '{msipath}', '/qb', """
                    r"""'TARGETDIR=\"%ProgramFiles%\"')"""
                    rf""" -Verb RunAs -Wait}}" """
                )
                if msipath is not None:
                    subprocess.call(command, shell=True)
                    shutil.rmtree(os.path.dirname(msipath))
            elif sys.platform == "darwin":
                arch = subprocess.check_output(["arch"], text=True).strip()
                if arch != "arm64":
                    # If QGIS is running under Rosetta2, then we get the wrong
                    # arch back. So check that too.
                    is_rosetta = subprocess.check_output(
                        ["sysctl", "-in", "sysctl.proc_translated"], text=True
                    ).strip()
                    if is_rosetta == "1":
                        arch = "arm64"
                    else:
                        arch = "x86_64"

                filename = MACOS_FILE.format(version=self.version, arch=arch)
                pkgpath = self._download(url, filename)
                command = f"open -W {pkgpath}"
                if pkgpath is not None:
                    subprocess.call(command, shell=True)
                    shutil.rmtree(os.path.dirname(pkgpath))
            else:
                url = RELEASE_URL.format(version=self.version)
                webbrowser.open_new_tab(url)
        except Exception as e:
            logging.error(str(e))
        finally:
            self.finished.emit()

    def _download(self, url, filename):
        fullurl = f"{url}/{filename}"
        logging.info(f"Downloading Kart from: {fullurl}")
        dirname = tempfile.mkdtemp()
        downloadpath = os.path.join(dirname, filename)
        chunk_size = 1024
        r = requests.get(fullurl, stream=True)
        file_size = r.headers.get("content-length") or 0
        file_size = int(file_size)
        percentage_per_chunk = 100.0 / (file_size / chunk_size)
        progress = 0
        with open(downloadpath, "wb") as f:
            for chunk in r.iter_content(chunk_size):
                f.write(chunk)
                progress += percentage_per_chunk
                self.downloadProgressChanged.emit(int(progress))

        self.downloadFinished.emit()
        return downloadpath


class InstallationWarningDialog(BASE, WIDGET):
    def __init__(self, msg: str, version: str):
        super(QDialog, self).__init__(iface.mainWindow())
        self.setupUi(self)
        self.version = version
        self.widgetDownload.setVisible(False)
        self.btnInstall.clicked.connect(self.install)
        self.btnOpenSettings.clicked.connect(self.openSettings)
        self.btnClose.clicked.connect(self.close)
        self.textBrowser.setText(msg)

    def install(self):
        try:
            self._install()
        except Exception:
            pass  # a later check will tell the user that kart could not be installed

    def _install(self):
        self.progressBar.setValue(0)
        self.widgetDownload.setVisible(True)
        self.btnClose.setEnabled(False)
        self.btnInstall.setEnabled(False)
        self.btnOpenSettings.setEnabled(False)
        t = DownloadAndInstallThread(self.version)
        loop = QEventLoop()
        t.downloadProgressChanged.connect(self.progressBar.setValue)
        t.downloadFinished.connect(self.hide)
        t.finished.connect(loop.exit, Qt.QueuedConnection)
        t.start()
        loop.exec_(flags=QEventLoop.ExcludeUserInputEvents)
        self.accept()

    def openSettings(self):
        self.accept()
        dlg = SettingsDialog()
        dlg.exec()
