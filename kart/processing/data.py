from qgis.core import (
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingOutputFolder,
)
from kart.gui import icons

from .base import KartAlgorithm
from kart.utils import tr

class RepoImportData(KartAlgorithm):
    REPO_PATH = "REPO_PATH"
    REPO_DATA_PATH = "REPO_DATA_PATH"
    REPO_DATASET_NAME = "REPO_DATASET_NAME"

    def displayName(self):
        return tr("Import Data")

    def shortHelpString(self):
        return tr("Import data into a repository")

    def icon(self):
        return icons.importIcon

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterFile(
                self.REPO_PATH,
                tr("Repo Path"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )

        self.addParameter(
            QgsProcessingParameterFile(
                self.REPO_DATA_PATH,
                tr("Data Path"),
                behavior=QgsProcessingParameterFile.File,
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.REPO_DATASET_NAME,
                tr("Dataset Name"),
                optional=True,
            )
        )

        self.addOutput(
            QgsProcessingOutputFolder(
                self.REPO_PATH,
                tr("Repo Path"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        from kart.kartapi import Repository

        repo_path = self.parameterAsFile(parameters, self.REPO_PATH, context)
        data_path = self.parameterAsFile(parameters, self.REPO_DATA_PATH, context)
        dataset_name = self.parameterAsString(
            parameters, self.REPO_DATASET_NAME, context
        )

        repo = Repository(repo_path)
        repo.importIntoRepo(data_path, dataset_name)

        return {
            self.REPO_PATH: repo_path,
            self.REPO_DATASET_NAME: dataset_name,
        }
