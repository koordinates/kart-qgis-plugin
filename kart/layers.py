import os
from functools import partial

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsFillSymbol,
    QgsGeometry,
    QgsMapLayer,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsTextAnnotation,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
from qgis.PyQt.QtCore import QPointF, QSizeF, Qt
from qgis.PyQt.QtGui import QColor, QTextDocument
from qgis.PyQt.QtWidgets import QAction, QInputDialog
from qgis.utils import iface

from kart.core import RepoManager
from kart.gui import icons
from kart.gui.diffviewer import DiffViewerDialog
from kart.gui.featurehistorydialog import FeatureHistoryDialog
from kart.gui.historyviewer import HistoryDialog
from kart.kartapi import executeskart
from kart.utils import AUTOCOMMIT, setting, tr


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
        self.rubberBands = {}

        self.mapTool = QgsMapToolEmitPoint(iface.mapCanvas())
        self.mapTool.canvasClicked.connect(self.canvasClicked)
        self.mapToolLayer = None

        self.showLogAction = QAction(icons.logIcon, tr("Show Log..."), iface)
        self.showLogAction.triggered.connect(_f(self.showLog))
        iface.addCustomActionForLayerType(
            self.showLogAction, "Kart", QgsMapLayer.LayerType.VectorLayer, False
        )

        self.showWorkingTreeChangesAction = QAction(
            icons.diffIcon, tr("Show working copy changes..."), iface
        )
        self.showWorkingTreeChangesAction.triggered.connect(_f(self.showWorkingTreeChanges))
        iface.addCustomActionForLayerType(
            self.showWorkingTreeChangesAction,
            "Kart",
            QgsMapLayer.LayerType.VectorLayer,
            False,
        )

        self.discardWorkingTreeChangesAction = QAction(
            icons.discardIcon, tr("Discard working copy changes..."), iface
        )
        self.discardWorkingTreeChangesAction.triggered.connect(_f(self.discardWorkingTreeChanges))
        iface.addCustomActionForLayerType(
            self.discardWorkingTreeChangesAction,
            "Kart",
            QgsMapLayer.LayerType.VectorLayer,
            False,
        )

        self.commitWorkingTreeChangesAction = QAction(
            icons.commitIcon, tr("Commit working copy changes..."), iface
        )
        self.commitWorkingTreeChangesAction.triggered.connect(_f(self.commitWorkingTreeChanges))
        iface.addCustomActionForLayerType(
            self.commitWorkingTreeChangesAction,
            "Kart",
            QgsMapLayer.LayerType.VectorLayer,
            False,
        )

        self.setMapToolAction = QAction(
            icons.crossIcon, tr("Activate 'show feature history' map tool"), iface
        )
        self.setMapToolAction.triggered.connect(_f(self.setMapTool))
        iface.addCustomActionForLayerType(
            self.setMapToolAction, "Kart", QgsMapLayer.LayerType.VectorLayer, False
        )

    @executeskart
    def _kartActiveLayerAndRepo(self):
        layers = []
        for layer in iface.layerTreeView().selectedLayers():
            repo = RepoManager.instance().repo_for_layer(layer)
            if repo is not None:
                layers.append((layer, repo))
        if len(layers) > 1:
            iface.pushMessage(
                "Kart",
                tr("There are more than one Kart layers selected"),
                level=Qgis.MessageLevel.Warning,
            )
            return None, None
        else:
            return layers[0]

    def layerAdded(self, layer):
        if isinstance(layer, QgsVectorLayer):
            repo = RepoManager.instance().repo_for_layer(layer)
            if repo is not None:
                func = _f(partial(self.commitLayerChanges, layer))
                layer.afterCommitChanges.connect(func)
                self.connected[layer] = func
                iface.addCustomActionForLayer(self.showLogAction, layer)
                iface.addCustomActionForLayer(self.showWorkingTreeChangesAction, layer)
                iface.addCustomActionForLayer(self.commitWorkingTreeChangesAction, layer)
                iface.addCustomActionForLayer(self.discardWorkingTreeChangesAction, layer)
                if layer.wkbType() != QgsWkbTypes.Type.NoGeometry:
                    iface.addCustomActionForLayer(self.setMapToolAction, layer)

                self.updateRubberBands()

    def addAnnotation(self, repo, rect, layer):
        symbol = QgsMarkerSymbol()
        symbol.setSize(0)
        fillSymbol = QgsFillSymbol.createSimple(
            {
                "color": "#ffffff",
                "color_border": "#000000",
                "width_border": "0",
                "style": "no",
                "style_border": "no",
            }
        )
        html = (
            f'<p style="color:{repo.boundingBoxColor.name()};">kart:'
            f"{repo.title() or os.path.basename(repo.path)}</p>"
        )
        doc = QTextDocument()
        doc.setHtml(html)
        annotation = QgsTextAnnotation(iface.mapCanvas())
        annotation.setMapPositionCrs(rect.crs())
        annotation.setMapPosition(QgsPointXY(rect.xMaximum(), rect.yMaximum()))
        annotation.setDocument(doc)
        annotation.setFillSymbol(fillSymbol)
        annotation.setFrameSize(QSizeF(doc.size().width(), doc.size().height()))
        annotation.setHasFixedMapPosition(True)
        annotation.setMarkerSymbol(symbol)
        annotation.setObjectName(f"kart:{layer.id()}")
        PT_MM = 25.4 / 72.0
        annotation.setFrameOffsetFromReferencePointMm(QPointF(-doc.size().width() * PT_MM, -5))
        QgsProject.instance().annotationManager().addAnnotation(annotation)

    def updateRubberBands(self):
        self.clearRubberBands()
        usedRepos = []
        for layer in QgsProject.instance().mapLayers().values():
            repo = RepoManager.instance().repo_for_layer(layer)
            if repo is not None and repo not in usedRepos:
                usedRepos.append(repo)
                rect = repo.spatialFilter()
                if rect is not None and repo.showBoundingBox:
                    rubberBand = QgsRubberBand(
                        iface.mapCanvas(), QgsWkbTypes.GeometryType.PolygonGeometry
                    )
                    rubberBand.setFillColor(QColor(0, 0, 0, 0))
                    rubberBand.setWidth(1)
                    rubberBand.setLineStyle(Qt.PenStyle.DotLine)
                    if repo.showBoundingBox:
                        rubberBand.setStrokeColor(repo.boundingBoxColor)
                    else:
                        rubberBand.setStrokeColor(QColor(0, 0, 0, 0))
                    self.rubberBands.append(rubberBand)
                    transform = QgsCoordinateTransform(
                        rect.crs(),
                        QgsProject.instance().crs(),
                        QgsProject.instance(),
                    )
                    geom = QgsGeometry.fromRect(rect)
                    geom.transform(transform)
                    rubberBand.setToGeometry(geom)
                    self.addAnnotation(repo, rect, layer)

    def clearRubberBands(self):
        for rubberBand in self.rubberBands:
            iface.mapCanvas().scene().removeItem(rubberBand)
        self.rubberBands = []
        for annotation in QgsProject.instance().annotationManager().annotations():
            if isinstance(
                annotation, QgsTextAnnotation
            ) and annotation.document().toPlainText().startswith("kart:"):
                try:
                    QgsProject.instance().annotationManager().removeAnnotation(annotation)
                except Exception:
                    pass

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
            QgsFeatureRequest().setFilterRect(r).setFlags(QgsFeatureRequest.Flag.ExactIntersect)
        )
        dataset = self.mapToolRepo.datasetNameFromLayer(self.mapToolLayer)
        idField = self.mapToolRepo.workingCopyLayerIdField(dataset)
        try:
            feature = next(feats)
            fid = feature[idField]
            history = self.mapToolRepo.log(dataset=dataset, featureid=fid)
            dlg = FeatureHistoryDialog(history, self.mapToolLayer, dataset, fid, self.mapToolRepo)
            dlg.exec()
        except StopIteration:
            iface.messageBar().pushMessage(
                "Kart",
                tr("No feature was found at the selected point."),
                level=Qgis.MessageLevel.Warning,
            )

    @executeskart
    def showLog(self):
        layer, repo = self._kartActiveLayerAndRepo()
        if layer is not None:
            dataset = repo.datasetNameFromLayer(layer)
            dialog = HistoryDialog(repo, dataset)
            dialog.exec()

    @executeskart
    def showWorkingTreeChanges(self):
        layer, repo = self._kartActiveLayerAndRepo()
        if layer is not None:
            dataset = repo.datasetNameFromLayer(layer)
            hasSchemaChanges = repo.diffHasSchemaChanges(dataset=dataset)
            if hasSchemaChanges:
                iface.messageBar().pushMessage(
                    tr("Changes"),
                    tr("There are schema changes in the working tree and changes cannot be shown"),
                    level=Qgis.MessageLevel.Warning,
                )
                return
            diff = repo.diff(dataset=dataset)
            if diff.get(dataset):
                dialog = DiffViewerDialog(
                    iface.mainWindow(), diff, repo, showRecoverNewButton=False
                )
                dialog.exec()
            else:
                iface.messageBar().pushMessage(
                    tr("Changes"),
                    tr("There are no changes in the working copy"),
                    level=Qgis.MessageLevel.Warning,
                )

    @executeskart
    def discardWorkingTreeChanges(self):
        layer, repo = self._kartActiveLayerAndRepo()
        if layer is not None:
            dataset = repo.datasetNameFromLayer(layer)
            repo.restore("HEAD", dataset)
            iface.messageBar().pushMessage(
                tr("Discard changes"),
                tr("Working copy changes for layer '{}' have been discarded").format(layer.name()),
                level=Qgis.MessageLevel.Info,
            )

    @executeskart
    def commitWorkingTreeChanges(self):
        layer, repo = self._kartActiveLayerAndRepo()
        if layer is not None:
            dataset = repo.datasetNameFromLayer(layer)
            changes = repo.changes().get(dataset, {})
            if changes:
                msg, ok = QInputDialog.getMultiLineText(
                    iface.mainWindow(), tr("Commit"), tr("Enter commit message:")
                )
                if ok and msg:
                    if repo.commit(msg, dataset=dataset):
                        iface.messageBar().pushMessage(
                            tr("Commit"),
                            tr("Changes correctly committed"),
                            level=Qgis.MessageLevel.Info,
                        )
                    else:
                        iface.messageBar().pushMessage(
                            tr("Commit"),
                            tr("Changes could not be committed"),
                            level=Qgis.MessageLevel.Warning,
                        )
            else:
                iface.messageBar().pushMessage(
                    tr("Commit"), tr("Nothing to commit"), level=Qgis.MessageLevel.Warning
                )

    def layerRemoved(self, layerid):
        self.updateRubberBands()

    @executeskart
    def commitLayerChanges(self, layer):
        repo = RepoManager.instance().repo_for_layer(layer)
        if repo is not None:
            auto = setting(AUTOCOMMIT)
            if auto:
                dataset = repo.datasetNameFromLayer(layer)
                repo.commit(f"Changed dataset '{dataset}'", dataset=dataset)
                iface.messageBar().pushMessage(
                    tr("Commit"),
                    tr("Changes correctly committed"),
                    level=Qgis.MessageLevel.Info,
                )

    def disconnectLayers(self):
        for layer, f in self.connected.items():
            layer.afterCommitChanges.disconnect(f)
