from typing import (
    Optional,
    List
)

from qgis.PyQt.QtCore import (
    QObject,
    pyqtSignal
)

from qgis.core import QgsMapLayer

from kart.utils import setting, setSetting

from ..kartapi import (
    Repository,
    KartException
)


class RepoManager(QObject):
    """
    Manages the local repositories
    """

    _instance: Optional['RepoManager'] = None

    repo_added = pyqtSignal(Repository)
    repo_removed = pyqtSignal(Repository)

    @classmethod
    def instance(cls) -> 'RepoManager':
        """
        Returns the repo manager instance
        """
        if not RepoManager._instance:
            RepoManager._instance = RepoManager()

        return RepoManager._instance

    def __init__(self):
        super().__init__()

        self._repos: List[Repository] = []

        self.read_repos_from_settings()

    def read_repos_from_settings(self):
        """
        Reads repos from user settings
        """
        s = setting("repos")
        if s is None:
            self._repos = []
        else:
            self._repos = []
            paths = s.split("|")
            for path in paths:
                repo = Repository(path)
                if repo.isInitialized():
                    self._repos.append(repo)
                    self.repo_added.emit(repo)

    def save_repos_to_settings(self):
        """
        Saves repos to user settings
        """
        s = "|".join([repo.path for repo in self._repos])
        setSetting("repos", s)

    def add_repo(self, repo: Repository):
        """
        Adds a repository to the manager
        """
        self._repos.append(repo)
        self.save_repos_to_settings()
        self.repo_added.emit(repo)

    def remove_repo(self, repo: Repository):
        """
        Removes a repository from the manager
        """
        for r in self._repos:
            if r.path == repo.path:
                self._repos.remove(r)
                break
        self.save_repos_to_settings()
        self.repo_removed.emit(repo)

    def repos(self) -> List[Repository]:
        """
        Returns the list of known repositories
        """
        return self._repos

    def repo_for_layer(self, layer: QgsMapLayer) -> Optional[Repository]:
        """
        Returns the repo matching a layer, or None if not found
        """
        try:
            for repo in self._repos:
                if repo.layerBelongsToRepo(layer):
                    return repo
        except KartException:
            pass

        return None
