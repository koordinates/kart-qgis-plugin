from functools import partial

from qgis.utils import iface
from qgis.core import Qgis

from qgis.PyQt.QtCore import QSettings

from kart.kartapi import repoForLayer


class LayerTracker:

    __instance = None
    @staticmethod
    def instance():
        if LayerTracker.__instance is None:
            LayerTracker()
        return LayerTracker.__instance

    def __init__(self):
        if LayerTracker.__instance is not None:
            raise Exception("Singleton class")

        LayerTracker.__instance = self

        self.connected = {}

    def layerAdded(self, layer):
        try:
            f = partial(self.commitLayerChanges, layer)
            layer.afterCommitChanges.connect(f)
            self.connected[layer] = f
        except AttributeError:
            pass

    def layerRemoved(self, layer):
        pass

    def commitLayerChanges(self, layer):
        repo = repoForLayer(layer)
        if repo is not None:
            auto = QSettings().value("kart/AutoCommit", False)
            if auto:
                name = layer.source().split("layername=")[-1]
                repo.commit(f"Changed layer '{name}'", layer=name)
                iface.messageBar().pushMessage(
                    "Commit", "Changes correctly committed", level=Qgis.Info
                )

    def disconnectLayers(self):
        for layer, f in self.connected.items():
            layer.afterCommitChanges.disconnect(f)