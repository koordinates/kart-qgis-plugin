from functools import partial

from qgis.utils import iface
from qgis.core import Qgis

from qgis.PyQt.QtCore import QSettings

from kart.kartapi import repoForLayer


class LayerTracker:
    def __init__(self):
        pass

    def layerAdded(self, layer):
        try:
            layer.afterCommitChanges.connect(partial(self.commitLayerChanges, layer))
        except AttributeError:
            print(1)
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
