import os
import re
import subprocess
import json
import tempfile

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import QApplication

from qgis.core import QgsMessageOutput

KART_EXECUTABLE = r"c:\program files\kart\kart.exe"

class KartException(Exception):
    pass


def executeskart(f):
    def inner(*args):
        try:
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
            msg = f'''
                <p><b>Kart failed with the following message:</b></p>
                <p style="color:red">{errors}</p>
                '''

            dlg.setMessage(msg, QgsMessageOutput.MessageHtml)
            dlg.showMessage()

    return inner


def isKartInstalled():
    try:
        ret = subprocess.run([KART_EXECUTABLE, "--version"],
                             stdout=subprocess.PIPE).stdout.decode('utf-8')
        return ret.startswith("Kart v")
    except Exception:
        return False


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


def saveRepos(repos):
    s = "|".join([repo.path for repo in repos])
    QSettings().setValue("kart/repos", s)


class Repository(object):
    def __init__(self, path):
        self.path = path

    def executeKart(self, commands, jsonoutput=False):
        commands.insert(0, KART_EXECUTABLE)
        if jsonoutput:
            commands.append("-ojson")
        os.chdir(self.path)
        print(commands)
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            ret = subprocess.Popen(commands,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   shell=True)
            stdout, stderr = ret.communicate()
            if ret.returncode:
                raise Exception(stderr.decode("utf-8"))
            '''
            print(stdout)
            print(stderr)
            '''
            if jsonoutput:
                return json.loads(stdout)
            else:
                return stdout.decode("utf-8")
        except Exception as e:
            raise KartException(str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def isInitialized(self):
        return os.path.exists(os.path.join(self.path, ".kart"))

    def init(self):
        self.executeKart(["init"], True)

    def importGpkg(self, path):
        self.executeKart(["import", f"GPKG:{path}"])

    def commit(self, msg, layer=None):
        commands = ["commit", "-m", msg]
        if layer is not None:
            commands.append(layer)
        self.executeKart(commands)

    def reset(self, ref="HEAD"):
        self.executeKart(["reset", ref])

    def log(self, ref="HEAD"):
        log = {c['commit']: c for c in self.executeKart(["log", ref], True)}
        logb = self.executeKart(["log", ref, "--graph", '--format=format:%H%n '])
        lines = logb.splitlines()
        lines.insert(0, "")
        lines.append("")
        commits = []
        for i in range(len(log)):
            commitline = lines[i * 2 + 1]
            commitid = commitline.split(" ")[-1]
            log[commitid]['commitColumn'] = (commitline.index("*")) // 2
            graph = []
            for j in range(3):
                graph.append({})
                for char in [r'\|', '/', r'\\']:
                    line = lines[i * 2 + j]
                    matches = re.finditer(char, line)
                    positions = [match.start() // 2 for match in matches]
                    graph[j][char] = positions
            log[commitid]['graph'] = graph
            commits.append(log[commitid])
        return commits

    def layers(self):
        return list(self.executeKart(["data", "ls"], True).values())[0]

    def branches(self):
        branches = list(self.executeKart(["branch"],
                                         True).values())[0]["branches"]
        return list(b.split("->")[-1].strip() for b in branches.keys())

    def checkoutBranch(self, branch):
        return self.executeKart(["checkout", branch])

    def createBranch(self, branch, commit="HEAD"):
        return self.executeKart(["branch", branch, commit])

    def deleteBranch(self, branch):
        return self.executeKart(["branch", "-d", branch])

    def mergeBranch(self, branch):
        return self.executeKart(["merge", branch])

    def abortMerge(self):
        return self.executeKart(["merge", "abort"])

    def continueMerge(self):
        return self.executeKart(["merge", "continue"])

    def createTag(self, tag, ref):
        return self.executeKart(["tag", tag, ref])

    def deleteTag(self, tag):
        return self.executeKart(["tag", "-d", tag])

    def diff(self, refa, refb):
        changes = {}
        try:
            commands = ["diff"]
            if refa and refb:
                commands.append(f"{refb}...{refa}")
            elif refa:
                commands.append(refa)
            elif refb:
                commands.append(refb)
            commands.append("-ogeojson")
            tmpdirname = tempfile.TemporaryDirectory()
            commands.extend(["--output", tmpdirname.name])
            self.executeKart(commands)
            for filename in os.listdir(tmpdirname.name):
                path = os.path.join(tmpdirname.name, filename)
                layername = os.path.splitext(filename)[0]
                with open(path) as f:
                    changes[layername] = json.load(f)['features']
            tmpdirname.cleanup()
        except:
            pass
        return changes

    def restore(self, ref, layer):
        if layer is not None:
            return self.executeKart(["restore", "-s", ref, layer])
        else:
            return self.executeKart(["restore", "-s", ref])

    def status(self):
        return list(self.executeKart(
            ["status"], True).values())[0]["workingCopy"].get("changes") or {}

    def isWorkingTreeClean(self):
        return bool(self.status())
