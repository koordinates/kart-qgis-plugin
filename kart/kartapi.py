import os
import subprocess
import json


def executeKart(self, commands, jsonoutput=False):
    commands.insert("kart", 0)
    if jsonoutput:
        commands.append("-ojson")
    os.chdir(self.path)
    ret = subprocess.run(commands, stdout=subprocess.PIPE).stdout.decode('utf-8')
    if jsonoutput:
        return json.loads(ret)
    else:
        return ret


def isKartInstalled():
    try:
        ret = executeKart(["--version"])
        return ret.startswith("Kart v")
    except Exception:
        return False


class Repository(object):

    def __init__(self, path):
        self.path = path

    def isInitialized(self):
        return os.path.exists(os.path.join(self.path, ".kart"))

    def init(self):
        executeKart(["init"], True)

    def importLayer(self, path):
        executeKart(["import", "GPKG:{path}"])

    def commit(self, msg):
        executeKart(["commit", msg])

    def reset(self):
        executeKart(["reset"])

    def log(self):
        return executeKart(["log"], True)

    def layers(self):
        return executeKart(["data", "ls"], True)

    def branches(self):
        return executeKart(["branch"], True)

    def checkoutBranch(self, branch):
        return executeKart(["checkout", branch])

    def createBranch(self, branch, commit="HEAD"):
        return executeKart(["branch", "-b", branch, commit])

    def deleteBranch(self, branch):
        return executeKart(["branch", "-d", branch])

    def diff(self, refa, refb):
        commands = ["diff"]
        if refa and refb:
            commands.append(f"{refa}...{refb}")
        elif refa:
            commands.append(refa)
        elif refb:
            commands.append(refb)
        return self.executeKart(commands, True)
