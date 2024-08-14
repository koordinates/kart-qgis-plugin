from qgis.core import QgsProcessingParameterFile, QgsProcessingParameterString
from kart.gui import icons

from .base import KartAlgorithm


class RepoCreateBranch(KartAlgorithm):
    REPO_PATH = "REPO_PATH"
    REPO_BRANCH_NAME = "REPO_BRANCH_NAME"

    def displayName(self):
        return self.tr("Create Branch")

    def shortHelpString(self):
        return self.tr("Create a new branch")

    def icon(self):
        return icons.createBranchIcon

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterFile(
                self.REPO_PATH,
                self.tr("Repo Path"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.REPO_BRANCH_NAME,
                self.tr("Branch Name"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        from kart.kartapi import Repository

        repo_path = self.parameterAsFile(parameters, self.REPO_PATH, context)
        branch_name = self.parameterAsString(parameters, self.REPO_REFISH, context)

        repo = Repository(repo_path)
        repo.createBranch(branch_name)

        return {
            self.REPO_PATH: repo_path,
        }


class RepoSwitchBranch(KartAlgorithm):
    REPO_PATH = "REPO_PATH"
    REPO_BRANCH_NAME = "REPO_BRANCH_NAME"

    def displayName(self):
        return self.tr("Switch to Branch")

    def shortHelpString(self):
        return self.tr("Switches to a named branch")

    def icon(self):
        return icons.checkoutIcon

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterFile(
                self.REPO_PATH,
                self.tr("Repo Path"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.REPO_BRANCH_NAME,
                self.tr("Branch Name"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        from kart.kartapi import Repository

        repo_path = self.parameterAsFile(parameters, self.REPO_PATH, context)
        branch_name = self.parameterAsString(parameters, self.REPO_BRANCH_NAME, context)

        repo = Repository(repo_path)
        repo.checkoutBranch(branch_name)

        return {
            self.REPO_PATH: repo_path,
        }


class RepoDeleteBranch(KartAlgorithm):
    REPO_PATH = "REPO_PATH"
    REPO_BRANCH_NAME = "REPO_BRANCH_NAME"

    def displayName(self):
        return self.tr("Delete Branch")

    def shortHelpString(self):
        return self.tr("Delete a branch")

    def icon(self):
        return icons.deleteIcon

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterFile(
                self.REPO_PATH,
                self.tr("Repo Path"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.REPO_BRANCH_NAME,
                self.tr("Branch Name"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        from kart.kartapi import Repository

        repo_path = self.parameterAsFile(parameters, self.REPO_PATH, context)
        branch_name = self.parameterAsString(parameters, self.REPO_BRANCH_NAME, context)

        repo = Repository(repo_path)
        repo.deleteBranch(branch_name)

        return {
            self.REPO_PATH: repo_path,
        }
