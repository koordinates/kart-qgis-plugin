from qgis.core import QgsProcessingParameterFile, QgsProcessingParameterString
from kart.gui import icons

from .base import KartAlgorithm
from kart.utils import tr

class RepoPushToRemote(KartAlgorithm):
    REPO_PATH = "REPO_PATH"
    REPO_BRANCH_NAME = "REPO_BRANCH_NAME"
    REPO_REMOTE_NAME = "REPO_REMOTE_NAME"

    def displayName(self):
        return tr("Push Changes to Remote")

    def shortHelpString(self):
        return tr("Sync changes in a repository to a remote location")

    def icon(self):
        return icons.pushIcon

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterFile(
                self.REPO_PATH,
                tr("Repo Path"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.REPO_BRANCH_NAME,
                tr("Branch Name"),
                defaultValue="main",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.REPO_REMOTE_NAME,
                tr("Remote Name"),
                defaultValue="origin",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        from kart.kartapi import Repository

        repo_path = self.parameterAsFile(parameters, self.REPO_PATH, context)
        branch_name = self.parameterAsString(parameters, self.REPO_BRANCH_NAME, context)
        remote_name = self.parameterAsString(parameters, self.REPO_REMOTE_NAME, context)

        repo = Repository(repo_path)
        repo.push(remote_name, branch_name)

        return {
            self.REPO_PATH: repo_path,
        }


class RepoPullFromRemote(KartAlgorithm):
    REPO_PATH = "REPO_PATH"
    REPO_BRANCH_NAME = "REPO_BRANCH_NAME"
    REPO_REMOTE_NAME = "REPO_REMOTE_NAME"

    def displayName(self):
        return tr("Pull Changes from Remote")

    def shortHelpString(self):
        return tr("Sync changes in a remote location to a local repository")

    def icon(self):
        return icons.pullIcon

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterFile(
                self.REPO_PATH,
                tr("Repo Path"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.REPO_BRANCH_NAME,
                tr("Branch Name"),
                defaultValue="main",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.REPO_REMOTE_NAME,
                tr("Remote Name"),
                defaultValue="origin",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        from kart.kartapi import Repository

        repo_path = self.parameterAsFile(parameters, self.REPO_PATH, context)
        branch_name = self.parameterAsString(parameters, self.REPO_BRANCH_NAME, context)
        remote_name = self.parameterAsString(parameters, self.REPO_REMOTE_NAME, context)

        repo = Repository(repo_path)
        repo.pull(remote_name, branch_name)

        return {
            self.REPO_PATH: repo_path,
        }
