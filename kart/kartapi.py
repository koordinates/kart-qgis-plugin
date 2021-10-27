import json
import locale
import math
import os
import re
import subprocess
import sys
import tempfile

from functools import partial

from urllib.parse import urlparse

from osgeo import gdal

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import (
    QApplication,
)

from qgis.core import (
    QgsDataSourceUri,
    QgsMessageOutput,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsRectangle,
    QgsReferencedRectangle,
    QgsVectorLayer,
)

from kart.gui.userconfigdialog import UserConfigDialog
from kart.gui.installationwarningdialog import InstallationWarningDialog

from kart.utils import progressBar
from kart import logging

SUPPORTED_VERSION = "0.10.4"


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
    if os.name == "nt":
        defaultFolder = os.path.join(os.environ["PROGRAMFILES"], "Kart")
    elif sys.platform == "darwin":
        defaultFolder = "Applications/Kart.app/Contents/MacOS/"
    else:
        defaultFolder = "/opt/kart/kart"
    folder = QSettings().value("kart/KartPath", "")
    folder = folder or defaultFolder
    for exe_name in ("kart.exe", "kart_cli", "kart"):
        path = os.path.join(folder, exe_name)
        if os.path.isfile(path):
            return path
    return path


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
        versionOk = (
            major == supported_major
            and minor == supported_minor
            and patch >= supported_patch
        )
        if not versionOk:
            url = (
                f"https://github.com/koordinates/kart/releases/tag/v{SUPPORTED_VERSION}"
            )
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


# Cached values, to avoid calling kart unless path is changed in settings

kartVersion = None
kartPath = None


def installedVersion():
    global kartVersion
    global kartPath
    path = QSettings().value("kart/KartPath", "")
    if path is not None and path == kartPath:
        return kartVersion
    else:
        try:
            version = executeKart(["--version"])
            if not version.startswith("Kart v"):
                raise Exception()
            else:
                versionnum = "".join(
                    [c for c in version.split(" ")[1] if c.isdigit() or c == "."]
                )
                kartVersion = versionnum
                kartPath = path
                return versionnum
        except Exception:
            kartVersion = None
            kartPath = None
            return None


def kartVersionDetails():
    path = QSettings().value("kart/KartPath", "")
    errtxt = (
        f"Kart is not correctly configured or installed. [Kart folder setting: {path}]"
    )
    try:
        version = executeKart(["--version"])
        if not version.startswith("Kart v"):
            return errtxt
        else:
            return version
    except Exception:
        return errtxt


def executeKart(commands, path=None, jsonoutput=False, feedback=None):
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

        with subprocess.Popen(
            commands,
            shell=os.name == "nt",
            env=executeKart.env,
            stdout=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding=encoding,
        ) as proc:
            if feedback is not None:
                output = []
                err = []
                for line in proc.stderr:
                    feedback(line)
                    err.append(line)
                for line in proc.stdout:
                    output.append(line)
                stdout = "".join(output)
                stderr = "".join(err)
            else:
                stdout, stderr = proc.communicate()
            logging.debug(f"Command output: {stdout}")
            if proc.returncode:
                raise Exception(stderr)
            if jsonoutput:
                return json.loads(stdout)
            else:
                return stdout
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


def _processProgressLine(bar, line):
    if "Writing dataset" in line:
        layername = line.split(":")[-1].strip()
        bar.setText(f"Checking out layer '{layername}'")
    elif line.startswith("Receiving objects: ") or line.startswith("Writing objects: "):
        tokens = line.split(": ")
        bar.setText(tokens[0])
        bar.setValue(math.floor(float(tokens[1][1 : tokens[1].find("%")].strip())))
    else:
        msg = line.split(" - ")[-1]
        if "%" in msg:
            matches = re.findall(r"(\d+(\.\d+)?)", msg)
            if matches:
                value = math.floor(float(matches[0][0]))
                bar.setValue(value)


class Repository:
    def __init__(self, path):
        self.path = path

    def executeKart(self, commands, jsonoutput=False):
        return executeKart(commands, self.path, jsonoutput)

    @staticmethod
    def clone(src, dst, location, extent=None):
        if "://" not in src:
            src = f"file://{src}"
        commands = ["-vv", "clone", src, dst, "--progress"]
        if location is not None:
            commands.extend(["--workingcopy", location])
        if extent is not None:
            kartExtent = f"{extent.crs().authid()};{extent.asWktPolygon()}"
            commands.extent(["--spatial-filter", kartExtent])

        with progressBar("Clone") as bar:
            bar.setText("Cloning repository")
            executeKart(commands, feedback=partial(_processProgressLine, bar))

        return Repository(dst)

    def title(self):
        with open(os.path.join(self.path, ".kart", "description")) as f:
            description = f.read()
        if description:
            if "unnamed" in description.lower():
                return ""
            else:
                return description.splitlines()[0]
        else:
            return ""

    def setTitle(self, title):
        with open(os.path.join(self.path, ".kart", "description"), "w") as f:
            f.write(title)

    def _config(self):
        ret = self.executeKart(["config", "-l"])
        lines = ret.splitlines()
        configDict = {}
        for line in lines:
            k, v = line.split("=")
            configDict[k] = v
        return configDict

    def spatialFilter(self):
        configDict = self._config()
        if "kart.spatialfilter.geometry" in configDict:
            crs = QgsCoordinateReferenceSystem(configDict["kart.spatialfilter.crs"])
            rect = QgsRectangle.fromWkt(configDict["kart.spatialfilter.geometry"])
            return QgsReferencedRectangle(rect, crs)
        else:
            return None

    def setSpatialFilter(self, extent=None):
        if extent:
            kartExtent = f"{extent.crs().authid()};{extent.asWktPolygon()}"
            self.executeKart(["checkout", "--spatial-filter", kartExtent])
        else:
            self.executeKart(["checkout", "--spatial-filter="])
        self.updateCanvas()

    def isInitialized(self):
        return os.path.exists(os.path.join(self.path, ".kart"))

    def init(self, location):
        if location is not None:
            self.executeKart(["init", "--workingcopy", location])
        else:
            self.executeKart(["init"])

    def importGpkg(self, path):
        self.executeKart(["import", f"GPKG:{path}"])

    def checkUserConfigured(self):
        configDict = self._config()
        if "user.name" in configDict and "user.email" in configDict:
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
        self.updateCanvas()

    def log(self, ref="HEAD", layername=None):
        if layername is not None:
            commands = ["log", "-ojson", ref, "--", "--", layername]
        else:
            commands = ["log", "-ojson", ref]
        ret = self.executeKart(commands)
        jsonRet = json.loads(ret)
        log = {c["commit"]: c for c in jsonRet}
        if layername is not None:
            commands = [
                "log",
                ref,
                "--graph",
                "--format=format:%H%n ",
                "--",
                "--",
                layername,
            ]
        else:
            commands = ["log", ref, "--graph", "--format=format:%H%n "]
        logb = self.executeKart(commands)
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

    def currentBranch(self):
        branch = list(self.executeKart(["branch"], True).values())[0]["current"]
        return branch

    def checkoutBranch(self, branch, force=False):
        if force:
            commands = ["checkout", "--force", branch]
        else:
            commands = ["checkout", branch]
        self.executeKart(commands)
        self.updateCanvas()

    def createBranch(self, branch, commit="HEAD"):
        return self.executeKart(["branch", branch, commit])

    def deleteBranch(self, branch):
        return self.executeKart(["branch", "-d", branch])

    def mergeBranch(self, branch, msg, noff=False, ffonly=False):
        commands = ["merge", branch]
        if msg:
            commands.extend(["--message", msg])
        if noff:
            commands.append("--no-ff")
        if ffonly:
            commands.append("--ff-only")
        ret = self.executeKart(commands, True)
        self.updateCanvas()
        return list(ret.values())[0].get("conflicts", [])

    def abortMerge(self):
        return self.executeKart(["merge", "--abort"])

    def continueMerge(self):
        return self.executeKart(["merge", "--continue", "-m", self.mergeMessage()])

    def tags(self):
        return self.executeKart(["tag"]).splitlines()

    def createTag(self, tag, ref):
        return self.executeKart(["tag", tag, ref])

    def deleteTag(self, tag):
        return self.executeKart(["tag", "-d", tag])

    def diff(self, refa=None, refb=None, layername=None):
        changes = {}
        try:
            commands = ["diff"]
            if refa and refb:
                commands.append(f"{refb}...{refa}")
            elif refa:
                commands.append(refa)
            else:
                commands.append("HEAD")
            if layername is not None:
                commands.append(layername)
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
        self.updateCanvas()

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
        self.updateCanvas()

    def remotes(self):
        remotes = {}
        ret = self.executeKart(["remote", "-v"], False)
        for line in ret.splitlines()[::2]:
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
        self.updateCanvas()
        return "kart conflicts" not in ret

    def layerBelongsToRepo(self, layer):
        location = self.workingCopyLocation()
        if location.lower().startswith("postgres"):
            uri = QgsDataSourceUri(layer.source())
            parse = urlparse(location)
            database, schema = parse.path.strip("/").split("/", 1)
            return uri.database() == database and uri.schema() == schema
        else:
            return os.path.normpath(self.path) in os.path.normpath(layer.source())

    def workingCopyLocation(self):
        return self._config()["kart.workingcopy.location"]

    def workingCopyLayer(self, layername):
        location = self.workingCopyLocation()
        path = os.path.join(self.path, location)
        if os.path.exists(path):
            layer = QgsVectorLayer(f"{path}|layername={layername}", layername)
            return layer
        elif location.lower().startswith("postgres"):
            parse = urlparse(location)
            host = parse.hostname or "localhost"
            port = parse.port or "5432"
            database, schema = parse.path.strip("/").split("/", 1)
            uri = QgsDataSourceUri()
            uri.setConnection(host, port, database)
            uri.setDataSource(schema, layername, "geom")
            layer = QgsVectorLayer(uri.uri(), layername, "postgres")
            return layer

    def workingCopyLayerIdField(self, layername):
        schema = self.executeKart(["meta", "get", layername, "schema.json"], True)[
            layername
        ]["schema.json"]
        for attr in schema:
            if attr.get("primaryKeyIndex") == 0:
                return attr["name"]

    def layerNameFromLayer(self, layer):
        location = self.workingCopyLocation()
        if location.lower().startswith("postgres"):
            uri = QgsDataSourceUri(layer.source())
            return uri.table()
        else:
            return layer.source().split("|")[-1].split("=")[-1]

    def deleteLayer(self, layername):
        # TODO handle case of layer not in gpkg-based repo
        name = os.path.basename(self.path)
        path = os.path.join(self.path, f"{name}.gpkg")
        ds = gdal.OpenEx(path, gdal.OF_UPDATE, allowed_drivers=["GPKG"])
        for i in range(ds.GetLayerCount()):
            if ds.GetLayer(i).GetName() == layername:
                ret = ds.DeleteLayer(i)
                if ret == 0:
                    self.commit(f"Removed layer {layername}", layername)
                else:
                    raise KartException("Could not delete layer from repository")

    def createPatch(self, ref, filename):
        self.executeKart(["show", "-ojson", "--output", filename, ref])

    def applyPatch(self, filename):
        self.executeKart(["apply", "--no-commit", filename])

    def updateCanvas(self):
        for layer in QgsProject.instance().mapLayers().values():
            if self.layerBelongsToRepo(layer):
                layer.triggerRepaint()
