import os
import json

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QTableWidgetItem,
    QListWidgetItem,
    QSizePolicy,
)
from qgis.PyQt.QtGui import QFont

from qgis.core import (
    edit,
    Qgis,
    QgsSymbol,
    QgsSingleSymbolRenderer,
    QgsWkbTypes,
    QgsProject,
    QgsJsonUtils,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas, QgsMapToolPan, QgsMessageBar
from qgis.utils import iface


WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "featurehistorydialog.ui")
)


class FeatureHistoryDialog(BASE, WIDGET):
    def __init__(self, history, workingCopyLayer, dataset, fid, repo):
        super(FeatureHistoryDialog, self).__init__(iface.mainWindow())
        self.history = history
        self.fid = fid
        self.repo = repo
        self.dataset = dataset
        self.layer = None
        self.workingCopyLayer = workingCopyLayer
        self.workingCopyLayerIdField = None
        self.workingCopyLayerCrs = None
        self.setupUi(self)
        self.setWindowFlags(Qt.Window)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout().insertWidget(0, self.bar)

        self.listCommits.currentRowChanged.connect(self.currentCommitChanged)
        self.btnRecover.clicked.connect(self.recoverVersion)

        horizontalLayout = QHBoxLayout()
        horizontalLayout.setSpacing(0)
        horizontalLayout.setMargin(0)
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(Qt.white)
        horizontalLayout.addWidget(self.canvas)
        self.canvasWidget.setLayout(horizontalLayout)
        self.panTool = QgsMapToolPan(self.canvas)
        self.canvas.setMapTool(self.panTool)

        for commit in history:
            item = CommitListItem(commit, workingCopyLayer, dataset, fid, repo)
            self.listCommits.addItem(item)

        self.listCommits.setCurrentRow(0)

    def _currentCommitFeature(self):
        row = self.listCommits.currentRow()
        if row == self.listCommits.count() - 1:
            if self.listCommits.count() == 1:
                return
            else:
                return self.listCommits.item(row - 1).oldFeature()
        else:
            return self.listCommits.currentItem().feature()

    def currentCommitChanged(self):
        commit = self.listCommits.currentItem().commit
        html = (
            f"<b>SHA-1:</b> {commit['commit']} <br>"
            f"<b>Date:</b> {commit['authorTime']} <br>"
            f"<b>Author:</b> {commit['authorName']} <br>"
            f"<b>Message:</b> {commit['message']} <br>"
            f"<b>Parents:</b> {', '.join(commit['parents'])} <br>"
        )
        self.commitDetails.setHtml(html)

        self.removeLayer()
        feature = self._currentCommitFeature()
        if feature is None:
            return
        geom = feature.geometry()
        attributes = feature.attributes()
        self.attributesTable.setRowCount(len(attributes))
        props = [f.name() for f in feature.fields()]
        for idx in range(len(props)):
            value = attributes[idx]
            font = QFont()
            font.setBold(True)
            font.setWeight(75)
            item = QTableWidgetItem(props[idx])
            item.setFont(font)
            self.attributesTable.setItem(idx, 0, item)
            self.attributesTable.setItem(idx, 1, QTableWidgetItem(str(value)))

        self.attributesTable.resizeRowsToContents()
        self.attributesTable.horizontalHeader().setMinimumSectionSize(150)
        self.attributesTable.horizontalHeader().setStretchLastSection(True)

        geomtype = QgsWkbTypes.displayString(geom.wkbType())
        if self.workingCopyLayerCrs is None:
            self.workingCopyLayerCrs = self.repo.workingCopyLayerCrs(self.dataset)
        self.layer = QgsVectorLayer(
            f"{geomtype}?crs={self.workingCopyLayerCrs}", "temp", "memory"
        )
        self.layer.dataProvider().addAttributes(self.workingCopyLayer.fields().toList())
        self.layer.updateFields()
        with edit(self.layer):
            self.layer.addFeature(feature)
        self.layer.updateExtents()
        self.layer.selectAll()
        self.layer.setExtent(self.layer.boundingBoxOfSelected())
        self.layer.invertSelection()
        symbol = QgsSymbol.defaultSymbol(self.layer.geometryType())
        symbol.setColor(Qt.green)
        symbol.setOpacity(0.5)
        self.layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        self.canvas.setRenderFlag(False)
        QgsProject.instance().addMapLayer(self.layer, False)
        self.canvas.setLayers([self.layer])
        self.canvas.setExtent(self.layer.extent())
        self.canvas.setRenderFlag(True)
        self.canvas.refresh()

    def recoverVersion(self):
        new = list(self.layer.getFeatures())[0]
        if self.workingCopyLayerIdField is None:
            self.workingCopyLayerIdField = self.repo.workingCopyLayerIdField(
                self.dataset
            )
        provider = self.workingCopyLayer.dataProvider()
        old = list(
            self.workingCopyLayer.getFeatures(
                f'"{self.workingCopyLayerIdField}" = {self.fid}'
            )
        )
        if old:
            provider.deleteFeatures([old[0].id()])
        provider.addFeatures([new])
        self.repo.updateCanvas()
        self.bar.pushMessage(
            "Feature history",
            "Working copy has been correctly modified",
            Qgis.Success,
            5,
        )

    def removeLayer(self):
        if self.layer is not None:
            QgsProject.instance().removeMapLayers([self.layer.id()])

    def closeEvent(self, evt):
        self.removeLayer()
        evt.accept()


class CommitListItem(QListWidgetItem):
    def __init__(self, commit, layer, dataset, fid, repo):
        QListWidgetItem.__init__(self)
        self.commit = commit
        self.layer = layer
        self.dataset = dataset
        self.repo = repo
        self.fid = fid
        self._feature = None
        self._oldFeature = None
        self.setText(f'{commit["message"].splitlines()[0]}')

    def feature(self):
        self._createFeatures()
        return self._feature

    def oldFeature(self):
        self._createFeatures()
        return self._oldFeature

    def _createFeatures(self):
        if self._feature is None:
            diff = self.repo.diff(
                self.commit["parents"][0],
                self.commit["commit"],
                self.dataset,
                self.fid,
            )
            geojson = diff[self.dataset][0]
            self._feature = QgsJsonUtils.stringToFeatureList(json.dumps(geojson))[0]
            props = geojson["properties"]
            self._feature.setFields(self.layer.fields())
            for prop in props:
                self._feature[prop] = props[prop]
            geojson = diff[self.dataset][-1]
            self._oldFeature = QgsJsonUtils.stringToFeatureList(json.dumps(geojson))[0]
            props = geojson["properties"]
            self._oldFeature.setFields(self.layer.fields())
            for prop in props:
                self._oldFeature[prop] = props[prop]
        return self._feature
