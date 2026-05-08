import difflib
import json
import locale
import os
import re
import subprocess
import sys
import tempfile
from functools import wraps
from typing import Callable, List, Optional
from urllib.parse import urlparse

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsDataSourceUri,
    QgsMessageOutput,
    QgsProject,
    QgsRectangle,
    QgsReferencedRectangle,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialog,
)
from qgis.utils import iface

from kart import logging
from kart.gui.installationwarningdialog import InstallationWarningDialog
from kart.gui.userconfigdialog import UserConfigDialog
from kart.utils import HELPERMODE, KARTPATH, setSetting, setting, tr

# Suppress console windows on Windows for all subprocess calls.
_POPEN_FLAGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
)

MINIMUM_SUPPORTED_VERSION = "0.14.0"
CURRENT_VERSION = "0.17.0"


class KartException(Exception):
    pass


class KartNotSupportedOperationException(Exception):
    pass


def executeskart(f):
    @wraps(f)
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
                # skip lines that refer to missing loads of shared libraries
                if line.startswith("ERROR 1: Can't load") or ".dylib" in line:
                    continue
                if "The specified procedure could not be found" in line:
                    continue
                if line.strip():
                    msglines.append(line)
            errors = "<br>".join(msglines)
            if "You have uncommitted changes" in errors:
                html_template = "<p><b>{text}</b></p>"
                msg = html_template.format(
                    text=tr(
                        "This operation requires a clean working tree. "
                        "Commit or discard your working tree changes and then retry."
                    )
                )
            else:
                html_template = "<p><b>{text}</b></p><p style='color:red'>{errors}</p>"
                msg = html_template.format(
                    text=tr("Kart failed with the following message:"),
                    errors=errors,
                )
            dlg.setMessage(msg, QgsMessageOutput.MessageType.MessageHtml)
            dlg.showMessage()

    return inner


def kartExecutable() -> str:
    """
    Returns the path to the kart executable
    """
    if os.name == "nt":
        defaultFolder = os.path.join(os.environ["PROGRAMFILES"], "Kart")
    elif sys.platform == "darwin":
        defaultFolder = "/Applications/Kart.app/Contents/MacOS/"
    else:
        defaultFolder = "/opt/kart"
    folder = setting(KARTPATH) or defaultFolder
    for exe_name in ("kart.exe", "kart_cli_helper", "kart_cli", "kart"):
        path = os.path.join(folder, exe_name)
        if os.path.isfile(path):
            return path
    return path


def checkKartInstalled(showMessage=True, useCache=True):
    version = installedVersion(useCache)
    supported_version_tuple = tuple(int(p) for p in MINIMUM_SUPPORTED_VERSION.split(".")[:3])

    msg = ""
    html_template = (
        "<p><b>{main_text}</b></p>"
        "<p>{hint_text} <a href='https://kartproject.org'>https://kartproject.org</a>.</p>"
    )

    hint_text = tr(
        "Click Install to download and install the latest Kart release. You can also download releases from"
    )

    if version is None:
        msg = html_template.format(
            main_text=tr(
                "Kart is not installed or your Kart installation location is not correctly configured."
            ),
            hint_text=hint_text,
        )
    else:
        version_tuple = tuple(int(p) for p in version.split(".")[:3])
        versionOk = version_tuple >= supported_version_tuple
        if not versionOk:
            msg = html_template.format(
                main_text=tr(
                    "The installed Kart version ({version}) is not supported by the plugin. Only versions {min_version} and later are supported."
                ).format(version=version, min_version=MINIMUM_SUPPORTED_VERSION),
                hint_text=hint_text,
            )

    if msg:
        if showMessage:
            dlg = InstallationWarningDialog(msg, CURRENT_VERSION)
            dlg.exec()
            installed = checkKartInstalled(showMessage=False, useCache=False)
            if installed:
                setSetting(KARTPATH, "")
                iface.messageBar().pushMessage(
                    tr("Install"),
                    tr("Kart has been correctly installed"),
                    level=Qgis.MessageLevel.Success,
                )
                return True
            else:
                iface.messageBar().pushMessage(
                    tr("Install"),
                    tr("Kart was not installed. Please install it manually."),
                    level=Qgis.MessageLevel.Warning,
                )
        return False
    else:
        return True


# Cached values, to avoid calling kart unless path is changed in settings

kartVersion = None
kartPath = None


def installedVersion(useCache=True):
    global kartVersion
    global kartPath
    path = setting(KARTPATH)
    if useCache and path is not None and path == kartPath:
        return kartVersion
    else:
        try:
            version = executeKart(["--version"], os.path.dirname(__file__))
            if not version.startswith("Kart v"):
                raise Exception()
            else:
                versionnum = "".join([c for c in version.split(" ")[1] if c.isdigit() or c == "."])
                kartVersion = versionnum
                kartPath = path
                return versionnum
        except Exception:
            kartVersion = None
            kartPath = None
            return None


def kartVersionDetails():
    path = setting(KARTPATH)
    errtxt = tr(
        "Kart is not correctly configured or installed. [Kart folder setting: {path}]"
    ).format(path=path)
    try:
        version = executeKart(["--version"], os.path.dirname(__file__))
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

    # The env PYTHONHOME/GDAL_DRIVER_PATH from QGIS can interfere with Kart.
    if not hasattr(executeKart, "env"):
        executeKart.env = os.environ.copy()
        if "PYTHONHOME" in executeKart.env:
            executeKart.env.pop("PYTHONHOME")
        if "GDAL_DRIVER_PATH" in executeKart.env:
            executeKart.env.pop("GDAL_DRIVER_PATH")
        # PYTHONPATH from QGIS causes kart's `import logging` to find the
        # plugin's kart/logging.py instead of the stdlib module.
        if "PYTHONPATH" in executeKart.env:
            executeKart.env.pop("PYTHONPATH")

    # always set the use helper env var as it is long lived and the setting may have changed
    executeKart.env["KART_USE_HELPER"] = "1" if setting(HELPERMODE) else ""

    # TODO - merge into Kart proper already
    logging.debug("Enabling VPC/VRTs generation...")
    executeKart.env["KART_POINT_CLOUD_VPCS"] = "1"
    executeKart.env["KART_RASTER_VRTS"] = "1"

    try:
        encoding = locale.getpreferredencoding(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        logging.debug(f"Command: {' '.join(commands)}")
        # TODO - all of this should be replaced by useage of QgsTask which
        #  will execute on a background thread. There are a number of
        #  ways in which this can deadlock
        with subprocess.Popen(
            commands,
            shell=os.name == "nt",
            env=executeKart.env,
            stdout=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding=encoding,
            cwd=path,
            **_POPEN_FLAGS,
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
                proc.communicate()  # need to get the returncode
            else:
                stdout, stderr = proc.communicate()
            logging.debug(f"Command output: {stdout}")
            if proc.returncode:
                raise KartException(stderr)
            if jsonoutput:
                return json.loads(stdout)
            else:
                return stdout
    except Exception as e:
        logging.error(str(e))
        raise KartException(str(e))
    finally:
        QApplication.restoreOverrideCursor()


def executeKartBinary(commands, path=None):
    """Like executeKart but returns raw bytes (for blob content)."""
    commands.insert(0, kartExecutable())

    if not hasattr(executeKart, "env"):
        executeKart.env = os.environ.copy()
        if "PYTHONHOME" in executeKart.env:
            executeKart.env.pop("PYTHONHOME")
        if "GDAL_DRIVER_PATH" in executeKart.env:
            executeKart.env.pop("GDAL_DRIVER_PATH")
        if "PYTHONPATH" in executeKart.env:
            executeKart.env.pop("PYTHONPATH")
        executeKart.env["KART_USE_HELPER"] = "1" if setting(HELPERMODE) else ""
        executeKart.env["KART_POINT_CLOUD_VPCS"] = "1"
        executeKart.env["KART_RASTER_VRTS"] = "1"

    try:
        with subprocess.Popen(
            commands,
            shell=os.name == "nt",
            env=executeKart.env,
            stdout=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=path,
            **_POPEN_FLAGS,
        ) as proc:
            stdout, stderr = proc.communicate()
            if proc.returncode:
                raise KartException(stderr.decode("utf-8", "replace"))
            return stdout
    except Exception as e:
        raise KartException(str(e))


class Repository:
    def __init__(self, path):
        self.path = path
        self.boundingBoxColor = QColor(150, 0, 0)
        self.showBoundingBox = True

    def executeKart(self, commands, jsonoutput=False):
        return executeKart(commands, self.path, jsonoutput)

    def executeKartBinary(self, commands):
        return executeKartBinary(commands, self.path)

    @staticmethod
    def supportedDbTypes():
        formats = {
            "PostgreSQL": "postgresql://",
            "SQL Server": "mssql://",
            "MySQL": "mysql://",
        }
        ret = executeKart(["import", "--list-formats"])
        supportedFormats = {}
        for name, protocol in formats.items():
            if protocol in ret:
                supportedFormats[name] = protocol

        return supportedFormats

    @staticmethod
    def tablesToImport(source):
        ret = executeKart(["import", "--list", source], jsonoutput=True)
        print(ret)
        return list(list(ret.values())[0].keys())

    @staticmethod
    def generate_clone_arguments(
        src: str,
        dst: str,
        location: Optional[str] = None,
        extent: Optional[QgsReferencedRectangle] = None,
        depth: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> List[str]:
        """
        Generates the clone command.

        Returns the list of kart executable arguments to perform the clone
        """
        src = os.path.expanduser(src)
        dst = os.path.expanduser(dst)
        if username and password:
            tokens = src.split("://")
            if len(tokens) == 2:
                src = f"{tokens[0]}://{username}:{password}@{tokens[1]}"
        commands = ["-vv", "clone", src, dst, "--progress"]
        if location is not None:
            commands.extend(["--workingcopy", location])
        if extent is not None:
            kart_extent = f"{extent.crs().authid()};{extent.asWktPolygon()}"
            commands.extend(["--spatial-filter", kart_extent])
        if depth is not None:
            commands.extend(["--depth", str(depth)])

        return commands

    @staticmethod
    def clone(
        src: str,
        dst: str,
        location: Optional[str] = None,
        extent: Optional[QgsReferencedRectangle] = None,
        depth: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        output_handler: Callable[[str], None] = None,
    ) -> "Repository":
        """
        Performs a (blocking, main thread only) clone operation
        """
        commands = Repository.generate_clone_arguments(
            src, dst, location, extent, depth, username, password
        )
        executeKart(commands, feedback=output_handler)
        return Repository(dst)

    def title(self):
        filepath = os.path.join(self.path, ".kart", "description")
        if not os.path.exists(filepath):
            return ""
        with open(filepath) as f:
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

    _configDict = None

    def _invalidateConfigCache(self):
        self._configDict = None

    def _config(self):
        if self._configDict is None:
            ret = self.executeKart(["config", "-l"])
            lines = ret.splitlines()
            self._configDict = {}
            for line in lines:
                tokens = line.split("=")
                if len(tokens) == 2:
                    self._configDict[tokens[0]] = tokens[1]
        return self._configDict

    def spatialFilter(self):
        configDict = self._config()
        if "kart.spatialfilter.geometry" in configDict:
            crs = QgsCoordinateReferenceSystem(configDict["kart.spatialfilter.crs"])
            rect = QgsRectangle.fromWkt(configDict["kart.spatialfilter.geometry"])
            return QgsReferencedRectangle(rect, crs)
        else:
            return None

    def setSpatialFilter(self, extent=None):
        if extent is not None:
            kartExtent = f"{extent.crs().authid()};{extent.asWktPolygon()}"
            self.executeKart(["checkout", "--spatial-filter", kartExtent])
        else:
            self.executeKart(["checkout", "--spatial-filter="])
        self._invalidateConfigCache()
        self.updateCanvas()

    def isInitialized(self):
        return os.path.exists(os.path.join(self.path, ".kart"))

    def init(self, location=None):
        if location is not None:
            self.executeKart(["init", "--workingcopy", location])
        else:
            self.executeKart(["init"])

    def importIntoRepo(self, source, dataset=None):
        importArgs = [source]
        if dataset:
            importArgs += ["--dataset", dataset]
        self.executeKart(["import"] + importArgs)

    def checkUserConfigured(self):
        configDict = self._config()
        # check user name/email are set and non-empty
        if all(configDict.get(configKey) for configKey in ("user.name", "user.email")):
            return True
        dlg = UserConfigDialog(configDict)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.configureUser(dlg.username, dlg.email)
            return True
        else:
            return False

    def configureUser(self, name, email):
        self.executeKart(["config", "--global", "user.name", name])
        self.executeKart(["config", "--global", "user.email", email])

    def commit(self, msg, dataset=None):
        if self.checkUserConfigured():
            commands = ["commit", "-m", msg, "--no-editor"]
            if dataset is not None:
                commands.append(dataset)
            self.executeKart(commands)
            return True
        else:
            return False

    def reset(self, ref="HEAD"):
        self.executeKart(["reset", ref, "-f"])
        self.updateCanvas()

    def log(self, ref="HEAD", dataset=None, featureid=None):
        if dataset is not None:
            if featureid is not None:
                filt = f"{dataset}:{featureid}"
            else:
                filt = dataset

            commands = ["log", "-ojson", ref, "--", filt]
        else:
            commands = ["log", "-ojson", ref]
        ret = self.executeKart(commands)
        jsonRet = json.loads(ret)
        log = {c["commit"]: c for c in jsonRet}
        if dataset is not None:
            commands = [
                "log",
                ref,
                "--graph",
                "-otext:%H%n",
                "--",
                filt,
            ]
        else:
            commands = ["log", ref, "--graph", "-otext:%H%n"]
        logb = self.executeKart(commands)
        lines = logb.splitlines()
        lines.insert(0, "")
        lines.append("")
        commitlinesidxs = []
        for i, line in enumerate(lines):
            if "*" in line:
                commitlinesidxs.append(i)
        commits = []
        for commitlineidx in commitlinesidxs:
            commitline = lines[commitlineidx]
            commitid = commitline.split(" ")[-1]
            log[commitid]["commitColumn"] = (commitline.index("*")) // 2
            graph = []
            for j in range(3):
                graph.append({})
                for char in [r"\|", "/", r"\\"]:
                    line = lines[commitlineidx - 1 + j]
                    matches = re.finditer(char, line)
                    positions = [match.start() // 2 for match in matches]
                    graph[j][char] = positions
            log[commitid]["graph"] = graph
            commits.append(log[commitid])
        return commits

    def datasets(self):
        vectorLayers = []
        tables = []
        meta = self.executeKart(["meta", "get"], True)
        for name, dataset in meta.items():
            crsProps = [k for k in dataset.keys() if k.startswith("crs/")]
            if crsProps:
                vectorLayers.append(name)
            else:
                tables.append(name)
        return vectorLayers, tables

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

    def mergeBranch(self, branch, msg="", noff=False, ffonly=False):
        commands = ["merge", branch, "--no-editor"]
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

    def diffHasSchemaChanges(self, refa=None, refb=None, dataset=None):
        commands = ["diff"]
        if refa and refb:
            commands.append(f"{refb}...{refa}")
        elif refa:
            commands.append(refa)
        else:
            commands.append("HEAD")
        if dataset is not None:
            commands.append(f"{dataset}:meta")
        else:
            commands.append("*:meta")
        ret = self.executeKart(commands, True)
        changes = list(ret.values())[0]
        schemaChanges = list(
            changes.get(name, {}).get("meta", {}).get("schema.json", None) for name in changes
        )
        return any(s is not None for s in schemaChanges)

    def diff(self, refa=None, refb=None, dataset=None, featureid=None):
        changes = {}
        try:
            commands = ["diff", "--output-format=geojson:extracompact"]
            if refa and refb:
                commands.append(f"{refb}...{refa}")
            elif refa:
                commands.append(refa)
            else:
                commands.append("HEAD")
            if dataset is not None:
                if featureid is not None:
                    commands.append(f"{dataset}:{featureid}")
                else:
                    commands.append(dataset)
            if dataset is not None and featureid is not None:
                ret = self.executeKart(commands)
                changes[dataset] = json.loads(ret)["features"]
            else:
                tmpdirname = tempfile.TemporaryDirectory()
                commands.extend(["--output", tmpdirname.name])
                self.executeKart(commands)
                for filename in os.listdir(tmpdirname.name):
                    path = os.path.join(tmpdirname.name, filename)
                    name = os.path.splitext(filename)[0]
                    with open(path) as f:
                        changes[name] = json.load(f)["features"]
                tmpdirname.cleanup()
        except Exception:
            pass
        return changes

    def restore(self, ref, dataset=None):
        if dataset is not None:
            self.executeKart(["restore", "-s", ref, dataset])
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

    def conflictsHaveSchemaChanges(self):
        ret = self.executeKart(["conflicts"], True)
        for datasetConflicts in list(ret.values())[0].values():
            schemaChanges = datasetConflicts.get("meta", {}).get("schema.json", None)
            if schemaChanges is not None:
                return True
        return False

    def conflicts(self):
        commands = ["conflicts", "--output-format=geojson:extracompact"]
        features = json.loads(self.executeKart(commands)).get("features", [])
        conflicts = {}
        for feature in features:
            dataset, elementtype, fid, version = feature["id"].split(":")
            if elementtype != "feature":
                raise KartNotSupportedOperationException()
            if dataset not in conflicts:
                conflicts[dataset] = {}
            if fid not in conflicts[dataset]:
                conflicts[dataset][fid] = {
                    "ancestor": None,
                    "theirs": None,
                    "ours": None,
                }
            conflicts[dataset][fid][version] = feature
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
        self.executeKart(["remote", "add", name, url])

    def removeRemote(self, name):
        self.executeKart(["remote", "remove", name])

    def push(self, remote, branch, push_all=False):
        if push_all:
            self.executeKart(["push", remote, "--all"])
        else:
            self.executeKart(["push", remote, branch])

    def pull(self, remote, branch):
        ret = self.executeKart(["pull", remote, branch, "--no-editor"])
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
            return f"{os.path.normpath(self.path)}{os.path.sep}" in os.path.normpath(
                layer.source()
            )

    def workingCopyLocation(self):
        return self._config()["kart.workingcopy.location"]

    def workingCopyLayer(self, dataset):
        location = self.workingCopyLocation()
        path = os.path.join(self.path, location)
        if os.path.exists(path):
            layer = QgsVectorLayer(f"{path}|layername={dataset}", dataset)
            return layer
        elif location.lower().startswith("postgres"):
            parse = urlparse(location)
            host = parse.hostname or "localhost"
            port = str(parse.port) if parse.port else "5432"
            database, schema = parse.path.strip("/").split("/", 1)
            username = parse.username
            password = parse.password
            uri = QgsDataSourceUri()
            uri.setConnection(host, port, database, username, password)
            uri.setDataSource(schema, dataset, "geom")
            layer = QgsVectorLayer(uri.uri(), dataset, "postgres")
            return layer

    def workingCopyLayerIdField(self, dataset):
        schema = self.executeKart(["meta", "get", dataset, "schema.json"], True)[dataset][
            "schema.json"
        ]
        for attr in schema:
            if attr.get("primaryKeyIndex") == 0:
                return attr["name"]

    def workingCopyLayerCrs(self, dataset):
        meta = self.executeKart(["meta", "get", dataset], True)[dataset]
        for k in meta.keys():
            if k.startswith("crs/"):
                return k[4:-4]

    def datasetNameFromLayer(self, layer):
        location = self.workingCopyLocation()
        if location.lower().startswith("postgres"):
            uri = QgsDataSourceUri(layer.source())
            return uri.table()
        else:
            return layer.source().split("|")[-1].split("=")[-1]

    def deleteDataset(self, dataset):
        self.executeKart(["data", "rm", "-m", f"Removed dataset {dataset}", dataset])

    def createPatch(self, ref, filename):
        self.executeKart(["show", "-ojson", "--output", filename, ref])

    def applyPatch(self, filename):
        self.executeKart(["apply", "--no-commit", filename])

    def updateCanvas(self):
        for layer in QgsProject.instance().mapLayers().values():
            if self.layerBelongsToRepo(layer):
                layer.triggerRepaint()

    def pathInsideRepo(self, path):
        repo_root = os.path.abspath(self.path)
        candidate = os.path.abspath(path)
        try:
            return os.path.commonpath([repo_root, candidate]) == repo_root
        except ValueError:
            return False

    def repoRelativePath(self, path):
        return os.path.relpath(
            os.path.abspath(path), os.path.abspath(self.path)
        ).replace(os.path.sep, "/")

    def validRepoRelativePath(self, rel_path):
        if not rel_path or os.path.isabs(rel_path):
            return False
        normalized = os.path.normpath(rel_path).replace(os.path.sep, "/")
        return normalized == rel_path and not normalized.startswith("../") and normalized != ".."

    def trackedAttachmentFiles(self, ref="HEAD"):
        """Return all tracked attachment files at *ref* via ``kart ls-files``."""
        out = self.executeKart(["ls-files", ref])
        return [line.strip() for line in out.splitlines() if line.strip()]

    def aheadBehind(self):
        """Return (ahead, behind) counts via ``kart ahead-behind``. Returns (0, 0) on failure."""
        try:
            out = self.executeKart(["ahead-behind"]).strip()
            parts = out.split()
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        except Exception:
            pass
        return 0, 0

    def fileStatus(self):
        """Return ``{"modified": [...], "untracked": [...], "deleted": [...]}`` for attachment files."""
        ret = self.executeKart(["status", "-ojson"])
        data = json.loads(ret)
        status = list(data.values())[0]
        files = (status.get("workingCopy") or {}).get("files")
        if files is None:
            return {"modified": [], "untracked": [], "deleted": []}
        return files

    def restoreFile(self, rel_path):
        """Restore *rel_path* in the working directory to its HEAD state."""
        self.executeKart(["restore", "-s", "HEAD", "--", rel_path])

    def readFileFromRepo(self, rel_path, ref="HEAD"):
        if not self.validRepoRelativePath(rel_path):
            raise KartException("Invalid repository-relative path")
        return self.executeKartBinary(["show-file", f"{ref}:{rel_path}"])

    def showFileAtRef(self, rel_path, ref="HEAD"):
        return self.readFileFromRepo(rel_path, ref)

    def blobHash(self, rel_path, ref="HEAD"):
        if not self.validRepoRelativePath(rel_path):
            raise KartException("Invalid repository-relative path")
        return self.executeKart(["blob-hash", f"{ref}:{rel_path}"]).strip()

    def fileDiff(self, rel_path):
        """Return a unified diff string comparing ``HEAD:<rel_path>`` to the working-directory file."""
        try:
            old_bytes = self.readFileFromRepo(rel_path)
            old_text = old_bytes.decode("utf-8", "replace")
            old_label = f"HEAD:{rel_path}"
        except Exception:
            old_text = ""
            old_label = f"HEAD:{rel_path} (new file)"

        full_path = os.path.join(self.path, rel_path.replace("/", os.sep))
        try:
            with open(full_path, encoding="utf-8", errors="replace") as f:
                new_text = f.read()
        except Exception:
            new_text = ""

        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=old_label,
                tofile=f"working copy:{rel_path}",
                lineterm="\n",
            )
        )

    def diffFile(self, rel_path, refa="HEAD~1", refb="HEAD"):
        if not self.validRepoRelativePath(rel_path):
            raise KartException("Invalid repository-relative path")
        try:
            old_bytes = self.readFileFromRepo(rel_path, refa)
            old_text = old_bytes.decode("utf-8", "replace")
        except KartException:
            old_text = ""
        try:
            new_bytes = self.readFileFromRepo(rel_path, refb)
            new_text = new_bytes.decode("utf-8", "replace")
        except KartException:
            new_text = ""
        return "".join(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"{refa}:{rel_path}",
                tofile=f"{refb}:{rel_path}",
                lineterm="\n",
            )
        )

    def diffFileAgainstPath(self, rel_path, source_path, ref="HEAD"):
        """Return a unified text diff between a repository blob and a file.

        Used for QGIS project saves: the candidate .qgs is written to a temporary
        file, the user reviews this diff before the file is committed.
        """
        if not self.validRepoRelativePath(rel_path):
            raise KartException("Invalid repository-relative path")

        try:
            old_bytes = self.showFileAtRef(rel_path, ref)
            old_text = old_bytes.decode("utf-8", "replace")
            old_label = f"{ref}:{rel_path}"
        except KartException:
            old_text = ""
            old_label = f"{ref}:{rel_path} (new file)"

        with open(source_path, "rb") as f:
            new_text = f.read().decode("utf-8", "replace")

        return "".join(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=old_label,
                tofile=f"working copy:{rel_path}",
                lineterm="\n",
            )
        )

    def commitFiles(self, message, files):
        """Commit attachment files via ``kart commit-files``.

        *files* is either a list of repo-relative paths (already in working copy)
        or a dict mapping repo-relative paths to source filesystem paths.
        """
        if not self.checkUserConfigured():
            return False
        cmd = ["commit-files", "-m", message]
        if isinstance(files, dict):
            for rel_path, src_path in files.items():
                cmd += [f"{rel_path}={src_path}"]
        else:
            cmd += list(files)
        self.executeKart(cmd)
        return True
