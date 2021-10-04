import json
import locale
import os
import re
import subprocess
import tempfile
import webbrowser

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import (
    QApplication,
    QVBoxLayout,
    QDialog,
    QTextBrowser,
    QDialogButtonBox,
)

from qgis.core import QgsMessageOutput, QgsProject
from qgis.utils import iface

from kart.gui.settingsdialog import SettingsDialog
from kart.gui.userconfigdialog import UserConfigDialog

from kart import logging

SUPPORTED_VERSION = "0.10.2"


class KartException(Exception):
    pass


class KartNotSupportedOperationException(Exception):
    pass


def executeskart(f):
    def inner(*args):
        try:
            if checkKartInstalled():
                return f(*args)
        except KartException as ex:
            dlg = QgsMessageOutput.createMessageOutput()
            dlg.setTitle("Kart")
            lines = str(ex).splitlines()
            msglines = []
            for line in lines:
                if line.startswith("ERROR 1: Can't load"):
                    continue
                if "The specified procedure could not be found" in line:
                    continue
                if line.strip():
                    msglines.append(line)
            errors = "<br>".join(msglines)
            msg = f"""
                <p><b>Kart failed with the following message:</b></p>
                <p style="color:red">{errors}</p>
                """
            dlg.setMessage(msg, QgsMessageOutput.MessageHtml)
            dlg.showMessage()

    return inner


def kartExecutable():
    folder = QSettings().value("kart/KartPath", "")
    for exe_name in ("kart.exe", "kart_cli", "kart"):
        path = os.path.join(folder, exe_name)
        if os.path.isfile(path):
            return path
    return path


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


def checkKartInstalled():
    version = installedVersion()
    supported_major, supported_minor, supported_patch = SUPPORTED_VERSION.split(".")
    msg = ""
    if version is None:
        url = "https://github.com/koordinates/kart#installing"
        msg = (
            "<p><b>Kart folder is not configured or Kart is not installed in the"
            f' specified folder</b></p><p><a href="{url}"> Install Kart </a>  if'
            ' needed and then <a href="settings"> configure <a> the Kart folder</p>.'
        )
    else:
        major, minor, patch = version.split(".")
        versionOk = major == supported_major and minor == supported_minor and patch >= supported_patch
        if not versionOk:
            url = f"https://github.com/koordinates/kart/releases/tag/v{SUPPORTED_VERSION}"
            msg = (
                f"<p><b>The installed Kart version ({version}) is different from the version"
                f" supported by the plugin ({SUPPORTED_VERSION})<b><p>"
                f' <p>Please <a href="{url}">install the supported version</a>.'
            )
    if msg:
        dlg = InstallationWarningDialog(msg)
        dlg.exec()
        return False
    else:
        return True


def installedVersion():
    try:
        version = executeKart(["--version"])
        if not version.startswith("Kart v"):
            return None
        else:
            return "".join(
                [c for c in version.split(" ")[1] if c.isdigit() or c == "."]
            )
    except Exception:
        return None


def executeKart(commands, path=None, jsonoutput=False):
    commands.insert(0, kartExecutable())
    if jsonoutput:
        commands.append("-ojson")
    if path is not None:
        os.chdir(path)

    # The env PYTHONHOME from QGIS can interfere with Kart.
    if not hasattr(executeKart, "env"):
        executeKart.env = os.environ.copy()
        executeKart.env.pop("PYTHONHOME")

    try:
        encoding = locale.getdefaultlocale()[1] or "utf-8"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        logging.debug(f"Command: {' '.join(commands)}")
        ret = subprocess.Popen(
            commands,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=executeKart.env,
            shell=os.name == "nt",
        )
        stdout, stderr = ret.communicate()
        output = stdout.decode(encoding)
        logging.debug(f"Command output: {output}")
        if ret.returncode:
            raise Exception(stderr.decode(encoding))
        if jsonoutput:
            return json.loads(output)
        else:
            return output
    except Exception as e:
        logging.error(str(e))
        raise KartException(str(e))
    finally:
        QApplication.restoreOverrideCursor()


def repos():
    s = QSettings().value("kart/repos", None)
    if s is None:
        return []
    else:
        repos = []
        paths = s.split("|")
        for path in paths:
            repo = Repository(path)
            if repo.isInitialized():
                repos.append(repo)
        return repos


def addRepo(repo):
    allrepos = repos()
    allrepos.append(repo)
    saveRepos(allrepos)


def removeRepo(repo):
    allrepos = repos()
    for r in allrepos:
        if r.path == repo.path:
            allrepos.remove(r)
            break
    saveRepos(allrepos)


def saveRepos(repos):
    s = "|".join([repo.path for repo in repos])
    QSettings().setValue("kart/repos", s)


def repoForLayer(layer):
    for repo in repos():
        if repo.layerBelongsToRepo(layer):
            return repo


class Repository:
    def __init__(self, path):
        self.path = path

    def executeKart(self, commands, jsonoutput=False):
        return executeKart(commands, self.path, jsonoutput)

    @staticmethod
    def clone(src, dst):
        executeKart(["clone", src, dst])
        return Repository(dst)

    def isInitialized(self):
        return os.path.exists(os.path.join(self.path, ".kart"))

    def init(self):
        self.executeKart(["init"])

    def importGpkg(self, path):
        self.executeKart(["import", f"GPKG:{path}"])

    def checkUserConfigured(self):
        ret = self.executeKart(["config", "-l"])
        if "user.name" in ret and "user.email" in ret:
            return True
        dlg = UserConfigDialog()
        if dlg.exec() == dlg.Accepted:
            self.executeKart(["config", "--global", "user.name", f"{dlg.username}"])
            self.executeKart(["config", "--global", "user.email", f"{dlg.email}"])
            return True
        else:
            return False

    def commit(self, msg, layer=None):
        if self.checkUserConfigured():
            commands = ["commit", "-m", msg]
            if layer is not None:
                commands.append(layer)
            self.executeKart(commands)
            return True
        else:
            return False

    def reset(self, ref="HEAD"):
        self.executeKart(["reset", ref, "-f"])
        self._updateCanvas()

    def log(self, ref="HEAD"):
        log = {c["commit"]: c for c in self.executeKart(["log", ref], True)}
        logb = self.executeKart(["log", ref, "--graph", "--format=format:%H%n "])
        lines = logb.splitlines()
        lines.insert(0, "")
        lines.append("")
        commits = []
        for i in range(len(log)):
            commitline = lines[i * 2 + 1]
            commitid = commitline.split(" ")[-1]
            log[commitid]["commitColumn"] = (commitline.index("*")) // 2
            graph = []
            for j in range(3):
                graph.append({})
                for char in [r"\|", "/", r"\\"]:
                    line = lines[i * 2 + j]
                    matches = re.finditer(char, line)
                    positions = [match.start() // 2 for match in matches]
                    graph[j][char] = positions
            log[commitid]["graph"] = graph
            commits.append(log[commitid])
        return commits

    def layers(self):
        return list(self.executeKart(["data", "ls"], True).values())[0]

    def branches(self):
        branches = list(self.executeKart(["branch"], True).values())[0]["branches"]
        return list(b.split("->")[-1].strip() for b in branches.keys())

    def checkoutBranch(self, branch):
        self.executeKart(["checkout", branch])
        self._updateCanvas()

    def createBranch(self, branch, commit="HEAD"):
        return self.executeKart(["branch", branch, commit])

    def deleteBranch(self, branch):
        return self.executeKart(["branch", "-d", branch])

    def mergeBranch(self, branch):
        ret = self.executeKart(["merge", branch], True)
        self._updateCanvas()
        return list(ret.values())[0].get("conflicts", [])

    def abortMerge(self):
        return self.executeKart(["merge", "--abort"])

    def continueMerge(self):
        return self.executeKart(["merge", "--continue", "-m", self.mergeMessage()])

    def createTag(self, tag, ref):
        return self.executeKart(["tag", tag, ref])

    def deleteTag(self, tag):
        return self.executeKart(["tag", "-d", tag])

    def diff(self, refa=None, refb=None):
        changes = {}
        try:
            commands = ["diff"]
            if refa and refb:
                commands.append(f"{refb}...{refa}")
            elif refa:
                commands.append(refa)
            elif refb:
                commands.append(refb)
            commands.extend(["-ogeojson", "--json-style", "extracompact"])
            tmpdirname = tempfile.TemporaryDirectory()
            commands.extend(["--output", tmpdirname.name])
            self.executeKart(commands)
            for filename in os.listdir(tmpdirname.name):
                path = os.path.join(tmpdirname.name, filename)
                layername = os.path.splitext(filename)[0]
                with open(path) as f:
                    changes[layername] = json.load(f)["features"]
            tmpdirname.cleanup()
        except Exception:
            pass
        return changes

    def restore(self, ref, layer=None):
        if layer is not None:
            self.executeKart(["restore", "-s", ref, layer])
        else:
            self.executeKart(["restore", "-s", ref])
        self._updateCanvas()

    def changes(self):
        return (
            list(self.executeKart(["status"], True).values())[0]
            .get("workingCopy", {})
            .get("changes")
            or {}
        )

    def isWorkingTreeClean(self):
        return not bool(self.changes())

    def isMerging(self):
        return os.path.exists(os.path.join(self.path, ".kart", "MERGE_MSG"))

    def mergeMessage(self):
        filepath = os.path.join(self.path, ".kart", "MERGE_MSG")
        msg = "Merge branch"
        if os.path.exists(filepath):
            with open(filepath) as f:
                msg = f.read()
        return msg

    def conflicts(self):
        commands = ["conflicts", "-ogeojson", "--json-style", "extracompact"]
        features = json.loads(self.executeKart(commands)).get("features", [])
        conflicts = {}
        for feature in features:
            layer, elementtype, fid, version = feature["id"].split(":")
            if elementtype != "feature":
                raise KartNotSupportedOperationException()
            if layer not in conflicts:
                conflicts[layer] = {}
            if fid not in conflicts[layer]:
                conflicts[layer][fid] = {"ancestor": None, "theirs": None, "ours": None}
            conflicts[layer][fid][version] = feature
        return conflicts

    def resolveConflicts(self, resolved):
        for fid, feature in resolved.items():
            if feature is not None:
                fc = {"type": "FeatureCollection", "features": [feature]}
                tmpfile = tempfile.NamedTemporaryFile("w+t", delete=False)
                json.dump(fc, tmpfile)
                tmpfile.close()
                self.executeKart(["resolve", "--with-file", tmpfile.name, fid])
                os.unlink(tmpfile.name)
            else:
                self.executeKart(["resolve", "--with", "delete", fid])
        self._updateCanvas()

    def remotes(self):
        remotes = {}
        ret = self.executeKart(["remote", "-v"], False)
        for line in ret.splitlines()[::2]:
            print(line)
            name, url = line.split("\t")
            remotes[name] = url.split(" ")[0]
        return remotes

    def addRemote(self, name, url):
        self.executeKart(["remote", "add", name, "url"])

    def removeRemote(self, name):
        self.executeKart(["remote", "remove", name])

    def push(self, remote, branch, push_all=False):
        if push_all:
            self.executeKart(["push", remote, "--all"])
        else:
            self.executeKart(["push", remote, branch])

    def pull(self, remote, branch):
        ret = self.executeKart(["pull", remote, branch])
        self._updateCanvas()
        return "kart conflicts" not in ret

    def layerBelongsToRepo(self, layer):
        return os.path.normpath(os.path.dirname(layer.source())) == os.path.normpath(
            self.path
        )

    def _updateCanvas(self):
        for layer in QgsProject.instance().mapLayers().values():
            if self.layerBelongsToRepo(layer):
                layer.triggerRepaint()
