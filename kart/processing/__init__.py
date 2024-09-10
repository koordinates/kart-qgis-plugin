from qgis.core import QgsProcessingProvider

from kart.gui import icons

from .branches import RepoCreateBranch, RepoDeleteBranch, RepoSwitchBranch
from .data import RepoImportData
from .remotes import RepoPullFromRemote, RepoPushToRemote
from .repos import RepoClone, RepoInit
from .tags import RepoCreateTag


class KartProvider(QgsProcessingProvider):
    def loadAlgorithms(self, *args, **kwargs):

        self.addAlgorithm(RepoInit())
        self.addAlgorithm(RepoClone())
        self.addAlgorithm(RepoCreateTag())
        self.addAlgorithm(RepoSwitchBranch())
        self.addAlgorithm(RepoCreateBranch())
        self.addAlgorithm(RepoDeleteBranch())
        self.addAlgorithm(RepoImportData())
        self.addAlgorithm(RepoPullFromRemote())
        self.addAlgorithm(RepoPushToRemote())

    def id(self, *args, **kwargs):
        return "Kart"

    def name(self, *args, **kwargs):
        return self.tr("Kart")

    def icon(self):
        return icons.kartIcon
