from functools import partial

from qgis.utils import iface
from qgis.core import (
    Qgis,
    QgsMapLayer,
    QgsVectorLayer,
    QgsFeatureRequest,
    QgsRectangle,
    edit,
)
from qgis.gui import QgsMapToolEmitPoint

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QAction, QInputDialog

from kart.gui.historyviewer import HistoryDialog
from kart.gui.diffviewer import DiffViewerDialog
from kart.gui.featurehistorydialog import FeatureHistoryDialog
from kart.kartapi import repoForLayer, executeskart


def _f(f, *args):
    def wrapper():
        f(*args)

    return wrapper


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

        self.mapTool = QgsMapToolEmitPoint(iface.mapCanvas())
        self.mapTool.canvasClicked.connect(self.canvasClicked)
        self.mapToolLayer = None

        self.showLogAction = QAction("Show Log...", iface)
        self.showLogAction.triggered.connect(_f(self.showLog))
        iface.addCustomActionForLayerType(
            self.showLogAction, "Kart", QgsMapLayer.VectorLayer, False
        )

        self.showWorkingTreeChangesAction = QAction(
            "Show working tree changes...", iface
        )
        self.showWorkingTreeChangesAction.triggered.connect(
            _f(self.showWorkingTreeChanges)
        )
        iface.addCustomActionForLayerType(
            self.showWorkingTreeChangesAction, "Kart", QgsMapLayer.VectorLayer, False
        )

        self.commitWorkingTreeChangesAction = QAction(
            "Commit working tree changes...", iface
        )
        self.commitWorkingTreeChangesAction.triggered.connect(
            _f(self.commitWorkingTreeChanges)
        )
        iface.addCustomActionForLayerType(
            self.commitWorkingTreeChangesAction, "Kart", QgsMapLayer.VectorLayer, False
        )

        self.setMapToolAction = QAction(
            "Activate 'show feature history' map tool", iface
        )
        self.setMapToolAction.triggered.connect(_f(self.setMapTool))
        iface.addCustomActionForLayerType(
            self.setMapToolAction, "Kart", QgsMapLayer.VectorLayer, False
        )

    @executeskart
    def _kartActiveLayerAndRepo(self):
        layers = []
        for layer in iface.layerTreeView().selectedLayers():
            repo = repoForLayer(layer)
            if repo is not None:
                layers.append((layer, repo))
        if len(layers) > 1:
            iface.pushMessage(
                "Kart",
                "There are more than one Kart layers selected",
                level=Qgis.Warning,
            )
            return None, None
        else:
            return layers[0]

    def layerAdded(self, layer):
        if isinstance(layer, QgsVectorLayer):
            repo = repoForLayer(layer)
            if repo is not None:
                func = _f(partial(self.commitLayerChanges, layer))
                layer.afterCommitChanges.connect(func)
                self.connected[layer] = func
                iface.addCustomActionForLayer(self.showLogAction, layer)
                iface.addCustomActionForLayer(self.showWorkingTreeChangesAction, layer)
                iface.addCustomActionForLayer(
                    self.commitWorkingTreeChangesAction, layer
                )
                iface.addCustomActionForLayer(self.setMapToolAction, layer)

    def setMapTool(self):
        layer, repo = self._kartActiveLayerAndRepo()
        if layer is not None:
            iface.mapCanvas().setMapTool(self.mapTool)
            self.mapToolLayer = layer
            self.mapToolRepo = repo

    def canvasClicked(self, pt, btn):
        searchRadius = iface.mapCanvas().extent().width() * 0.005
        r = QgsRectangle(pt, pt)
        r.grow(searchRadius)
        r = self.mapTool.toLayerCoordinates(self.mapToolLayer, r)

        feats = self.mapToolLayer.getFeatures(
            QgsFeatureRequest()
            .setFilterRect(r)
            .setFlags(QgsFeatureRequest.ExactIntersect)
        )
        layername = self.mapToolRepo.layerNameFromLayer(self.mapToolLayer)
        idField = self.mapToolRepo.workingCopyLayerIdField(layername)
        try:
            feature = next(feats)
            fid = feature[idField]
            history = self.mapToolRepo.log(layername=layername, featureid=fid)
            dlg = FeatureHistoryDialog(
                history, self.mapToolLayer, layername, fid, self.mapToolRepo
            )
            dlg.exec()
        except StopIteration:
            iface.pushMessage(
                "Kart",
                "No feature was found at the selected point.",
                level=Qgis.Warning,
            )

    @executeskart
    def showLog(self):
        layer, repo = self._kartActiveLayerAndRepo()
        if layer is not None:
            layername = repo.layerNameFromLayer(layer)
            dialog = HistoryDialog(repo, layername)
            dialog.exec()

    @executeskart
    def showWorkingTreeChanges(self):
        layer, repo = self._kartActiveLayerAndRepo()
        if layer is not None:
            layername = repo.layerNameFromLayer(layer)
            changes = repo.diff(layername=layername)
            if changes.get(layername):
                dialog = DiffViewerDialog(iface.mainWindow(), changes, repo)
                dialog.exec()
            else:
                iface.messageBar().pushMessage(
                    "Changes",
                    "There are no changes in the working tree",
                    level=Qgis.Warning,
                )

    @executeskart
    def commitWorkingTreeChanges(self):
        layer, repo = self._kartActiveLayerAndRepo()
        if layer is not None:
            layername = repo.layerNameFromLayer(layer)
            changes = repo.changes().get(layername, {})
            if changes:
                msg, ok = QInputDialog.getMultiLineText(
                    iface.mainWindow(), "Commit", "Enter commit message:"
                )
                if ok and msg:
                    if repo.commit(msg, layer=layername):
                        iface.messageBar().pushMessage(
                            "Commit", "Changes correctly committed", level=Qgis.Info
                        )
                    else:
                        iface.messageBar().pushMessage(
                            "Commit",
                            "Changes could not be commited",
                            level=Qgis.Warning,
                        )
            else:
                iface.messageBar().pushMessage(
                    "Commit", "Nothing to commit", level=Qgis.Warning
                )

    def layerRemoved(self, layer):
        pass

    @executeskart
    def commitLayerChanges(self, layer):
        repo = repoForLayer(layer)
        if repo is not None:
            auto = QSettings().value("kart/AutoCommit", False, type=bool)
            if auto:
                layername = repo.layerNameFromLayer(layer)
                repo.commit(f"Changed layer '{layername}'", layer=layername)
                iface.messageBar().pushMessage(
                    "Commit", "Changes correctly committed", level=Qgis.Info
                )

    def disconnectLayers(self):
        for layer, f in self.connected.items():
            layer.afterCommitChanges.disconnect(f)
