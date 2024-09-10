from qgis.core import QgsProcessingParameterFile, QgsProcessingParameterString
from kart.gui import icons

from .base import KartAlgorithm


class RepoCreateTag(KartAlgorithm):
    REPO_PATH = "REPO_PATH"
    REPO_TAG_NAME = "REPO_TAG_NAME"

    def displayName(self):
        return self.tr("Create Tag")

    def shortHelpString(self):
        return self.tr("Create a new tag")

    def icon(self):
        return icons.propertiesIcon

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
                self.REPO_TAG_NAME,
                self.tr("Tag Name"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        from kart.kartapi import Repository

        repo_path = self.parameterAsFile(parameters, self.REPO_PATH, context)
        tag_name = self.parameterAsString(parameters, self.REPO_TAG_NAME, context)

        repo = Repository(repo_path)
        repo.createTag(tag_name)

        return {
            self.REPO_PATH: repo_path,
            self.REPO_TAG_NAME: tag_name,
        }
