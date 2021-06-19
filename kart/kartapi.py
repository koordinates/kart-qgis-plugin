import os
import subprocess
import json

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import QApplication

KART_EXECUTABLE = r"c:\program files\kart\kart.exe"

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
                                 shell=True)
            stdout, stderr = ret.communicate()
            print (ret.returncode)
            if jsonoutput:
                return json.loads(stdout)
            else:
                return stdout.decode("utf-8")
        except:
            raise
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

    def reset(self, ref = "HEAD"):
        self.executeKart(["reset", ref])

    def log(self, ref = "HEAD"):
        log = self.executeKart(["log", ref], True)
        logb = self.executeKart(["log", "--graph", "--oneline"])
        i = 0
        for line in logb.splitlines():
            if "*" in line:
                log[i]['commitColumn'] = (line.index("*")) // 2
                i += 1
        return log

    def layers(self):
        return list(self.executeKart(["data", "ls"], True).values())[0]

    def branches(self):
        branches = list(self.executeKart(["branch"], True).values())[0]["branches"]
        return list(branches.keys())

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

    def diff(self, refa, refb):
        commands = ["diff"]
        if refa and refb:
            commands.append(f"{refb}...{refa}")
        elif refa:
            commands.append(refa)
        elif refb:
            commands.append(refb)
        return self.executeKart(commands, True).values()[0]

    def status(self):
        return list(self.executeKart(["status"], True).values())[0]["workingCopy"].get("changes") or {}

    def isWorkingTreeClean(self):
        return bool(self.status())

