# -*- coding: utf-8 -*-

import os
import json
import difflib

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QColor, QBrush
from qgis.PyQt.QtWidgets import (
    QVBoxLayout,
    QTableWidgetItem,
    QHeaderView,
    QTreeWidgetItem,
    QDialog,
    QTreeWidgetItemIterator,
    QSizePolicy,
)

from qgis.core import (
    edit,
    QgsProject,
    QgsFeature,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsJsonUtils,
    QgsMarkerSymbol,
    QgsLineSymbol,
    QgsFillSymbol,
    QgsCoordinateReferenceSystem,
    Qgis,
    QgsGeometry,
    QgsPointXY,
)

from qgis.utils import iface
from qgis.gui import QgsMapCanvas, QgsMessageBar, QgsMapToolPan

from .mapswipetool import MapSwipeTool

ADDED, MODIFIED, REMOVED, UNCHANGED = 0, 1, 2, 3

NO_LAYERS = 0
PROJECT_LAYERS = 1
OSM_BASEMAP = 2

TRANSPARENCY = 0
SWIPE = 1
VERTEX_DIFF = 2

pluginPath = os.path.split(os.path.dirname(__file__))[0]


def icon(f):
    return QIcon(os.path.join(pluginPath, "img", f))


layerIcon = icon("layer_group.svg")
featureIcon = icon("geometry.png")
addedIcon = icon("add.png")
removedIcon = icon("remove.png")
modifiedIcon = icon("edit.png")

pointsStyle = os.path.join(pluginPath, "resources", "geomdiff_points.qml")

WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "diffviewerwidget.ui")
)


class DiffViewerDialog(QDialog):
    def __init__(self, parent, changes, repo):
        super(QDialog, self).__init__(parent)
        self.setWindowFlags(Qt.Window)
        layout = QVBoxLayout()
        layout.setMargin(0)
        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        layout.addWidget(self.bar)
        self.history = DiffViewerWidget(changes, repo)
        self.history.workingLayerChanged.connect(self.workingLayerChanged)
        layout.addWidget(self.history)
        self.setLayout(layout)
        self.resize(1024, 768)
        self.setWindowTitle("Diff viewer")

    def workingLayerChanged(self):
        self.bar.pushMessage(
            "Diff", "Working copy has been correctly modified", Qgis.Success, 5
        )

    def closeEvent(self, evt):
        self.history.removeMapLayers()
        evt.accept()


class DiffViewerWidget(WIDGET, BASE):

    workingLayerChanged = pyqtSignal()

    def __init__(self, changes, repo):
        super(DiffViewerWidget, self).__init__()
        self.changes = changes
        self.repo = repo
        self.oldLayer = None
        self.newLayer = None
        self.osmLayer = None
        self.vertexDiffLayer = None
        self.currentFeature = None
        self.workingCopyLayers = {}
        self.workingCopyLayersIdFields = {}
        self.workingCopyLayerCrs = {}

        self.setupUi(self)

        self.setWindowFlags(self.windowFlags() | Qt.WindowSystemMenuHint)

        self.canvas = QgsMapCanvas(self.canvasWidget)
        tabLayout = QVBoxLayout()
        tabLayout.setMargin(0)
        tabLayout.addWidget(self.canvas)
        self.canvasWidget.setLayout(tabLayout)

        self.sliderTransparencyOld.setValue(100)
        self.sliderTransparencyNew.setValue(100)

        self.sliderTransparencyNew.valueChanged.connect(self.setTransparencyNew)
        self.sliderTransparencyOld.valueChanged.connect(self.setTransparencyOld)
        self.comboDiffType.currentIndexChanged.connect(self.fillCanvas)
        self.comboAdditionalLayers.currentIndexChanged.connect(self.fillCanvas)
        self.btnRecoverOldVersion.clicked.connect(self.recoverOldVersion)
        self.btnRecoverNewVersion.clicked.connect(self.recoverNewVersion)
        self.featuresTree.currentItemChanged.connect(self.treeItemChanged)
        self.featuresTree.header().hide()

        self.featuresTree.header().setStretchLastSection(True)

        self.fillTree()

        self.selectFirstChangedFeature()

    def selectFirstChangedFeature(self):
        iterator = QTreeWidgetItemIterator(self.featuresTree)
        while iterator.value():
            item = iterator.value()
            if isinstance(item, FeatureItem):
                self.featuresTree.setCurrentItem(item)
                return
            iterator += 1

    def treeItemChanged(self, current, previous):
        if not isinstance(current, FeatureItem):
            self.attributesTable.setVisible(False)
            self.canvasWidget.setVisible(False)
            self.grpTransparency.setVisible(False)
            self.widgetDiffConfig.setVisible(False)
        else:
            self.attributesTable.setVisible(True)
            self.canvasWidget.setVisible(True)
            self.grpTransparency.setVisible(True)
            self.widgetDiffConfig.setVisible(True)
            self.currentFeature = current
            self.fillAttributesDiff()
            self.removeMapLayers()
            self._createLayers()
            self.fillCanvas()

    def fillAttributesDiff(self):
        old = self.currentFeature.old
        new = self.currentFeature.new
        self.attributesTable.clear()
        fields = []
        fields.extend(new.get("properties", {}).keys())
        fields.extend(old.get("properties", {}).keys())
        fields = list(set(fields))

        changeTypeColor = [Qt.green, QColor(255, 170, 0), Qt.red, Qt.white]
        changeTypeName = ["Added", "Modified", "Removed", "Unchanged"]
        self.attributesTable.clear()
        self.attributesTable.verticalHeader().show()
        self.attributesTable.horizontalHeader().show()
        labels = fields + ["geometry"]
        self.attributesTable.setRowCount(len(labels))
        self.attributesTable.setVerticalHeaderLabels(labels)
        self.attributesTable.setHorizontalHeaderLabels(
            ["Old value", "New value", "Change type"]
        )
        for i, attrib in enumerate(fields):
            try:
                if not bool(old):
                    newvalue = new["properties"].get(attrib)
                    oldvalue = ""
                    changeType = ADDED
                elif not bool(new):
                    oldvalue = old["properties"].get(attrib)
                    newvalue = ""
                    changeType = REMOVED
                else:
                    oldvalue = old["properties"].get(attrib)
                    newvalue = new["properties"].get(attrib)
                    if oldvalue != newvalue:
                        changeType = MODIFIED
                    else:
                        changeType = UNCHANGED
            except Exception:
                oldvalue = newvalue = ""
                changeType = UNCHANGED

            self.attributesTable.setItem(i, 0, DiffItem(oldvalue))
            self.attributesTable.setItem(i, 1, DiffItem(newvalue))
            self.attributesTable.setItem(i, 2, DiffItem(changeTypeName[changeType]))
            for col in range(3):
                cell = self.attributesTable.item(i, col)
                if cell is not None:
                    cell.setBackground(QBrush(changeTypeColor[changeType]))

        row = len(fields)
        if not bool(old):
            newvalue = new["geometry"]
            oldvalue = ""
            changeType = ADDED
        elif not bool(new):
            oldvalue = old["geometry"]
            newvalue = ""
            changeType = REMOVED
        else:
            oldvalue = old["geometry"]
            newvalue = new["geometry"]
            if oldvalue != newvalue:
                changeType = MODIFIED
            else:
                changeType = UNCHANGED
        self.attributesTable.setItem(row, 0, DiffItem(oldvalue))
        self.attributesTable.setItem(row, 1, DiffItem(newvalue))
        self.attributesTable.setItem(row, 2, DiffItem(changeTypeName[changeType]))

        for col in range(3):
            try:
                self.attributesTable.item(row, col).setBackground(
                    QBrush(changeTypeColor[changeType])
                )
            except Exception:
                pass

        self.attributesTable.horizontalHeader().setMinimumSectionSize(88)
        self.attributesTable.resizeColumnsToContents()
        header = self.attributesTable.horizontalHeader()
        for column in range(header.count()):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            width = header.sectionSize(column)
            header.resizeSection(column, width)
            header.setSectionResizeMode(column, QHeaderView.Interactive)

    def fillTree(self):
        self.featuresTree.clear()
        for layer, changes in self.changes.items():
            layerItem = QTreeWidgetItem()
            layerItem.setText(0, layer)
            layerItem.setIcon(0, layerIcon)
            addedItem = QTreeWidgetItem()
            addedItem.setText(0, "Added")
            addedItem.setIcon(0, addedIcon)
            removedItem = QTreeWidgetItem()
            removedItem.setText(0, "Removed")
            removedItem.setIcon(0, removedIcon)
            modifiedItem = QTreeWidgetItem()
            modifiedItem.setText(0, "Modified")
            modifiedItem.setIcon(0, modifiedIcon)

            subItems = {"I": addedItem, "U": modifiedItem, "D": removedItem}
            changes = {feat["id"]: feat for feat in changes}
            usedids = []
            for feat in changes.values():
                changetype, featid = feat["id"].split("::")
                changetype = changetype[0]
                if featid not in usedids:
                    if changetype == "I":
                        old = {}
                        new = feat
                    elif changetype == "D":
                        old = feat
                        new = {}
                    else:
                        old = changes[f"U-::{featid}"]
                        new = changes[f"U+::{featid}"]
                    usedids.append(featid)
                    item = FeatureItem(featid, old, new, layer)
                    subItems[changetype].addChild(item)

            for subItem in subItems.values():
                if subItem.childCount():
                    layerItem.addChild(subItem)
            if layerItem.childCount():
                self.featuresTree.addTopLevelItem(layerItem)

        self.attributesTable.clear()
        self.attributesTable.verticalHeader().hide()
        self.attributesTable.horizontalHeader().hide()

        self.featuresTree.expandAll()

    def fillCanvas(self):
        self.canvas.setLayers([])
        layername = self.currentFeature.layer
        crs = QgsCoordinateReferenceSystem(self.workingCopyLayerCrs[layername])
        self.canvas.setDestinationCrs(crs)
        QgsProject.instance().addMapLayer(self.newLayer, False)
        QgsProject.instance().addMapLayer(self.oldLayer, False)
        layers = []

        ref = self.currentFeature.new or self.currentFeature.old
        geomtype = ref["geometry"]["type"]
        geomclass = {
            "Point": QgsMarkerSymbol,
            "Line": QgsLineSymbol,
            "Polygon": QgsFillSymbol,
        }
        self.mapTool = QgsMapToolPan(self.canvas)
        symbol = geomclass.get(geomtype, QgsFillSymbol).createSimple(
            {"color": "0,255,0,255"}
        )
        self.newLayer.renderer().setSymbol(symbol)
        symbol = geomclass.get(geomtype, QgsFillSymbol).createSimple(
            {"color": "255,0,0,255"}
        )
        self.oldLayer.renderer().setSymbol(symbol)
        layers.extend([self.newLayer, self.oldLayer])
        if self.comboDiffType.currentIndex() == SWIPE:
            self.mapTool = MapSwipeTool(self.canvas, [self.newLayer])
            layers.remove(self.newLayer)
        elif self.comboDiffType.currentIndex() == VERTEX_DIFF:
            symbol = geomclass.get(geomtype, QgsFillSymbol).createSimple(
                {"color": "255,255,255,255"}
            )
            self.newLayer.renderer().setSymbol(symbol)
            symbol = geomclass.get(geomtype, QgsFillSymbol).createSimple(
                {"color": "255,255,255,255"}
            )
            self.oldLayer.renderer().setSymbol(symbol)
            layers.insert(0, self.vertexDiffLayer)
        if self.comboAdditionalLayers.currentIndex() == PROJECT_LAYERS:
            layers.extend(iface.mapCanvas().layers())
        elif self.comboAdditionalLayers.currentIndex() == OSM_BASEMAP:
            uri = "crs=EPSG:3857&type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0"
            self.osmLayer = QgsRasterLayer(uri, "OSM", "wms")
            QgsProject.instance().addMapLayer(self.osmLayer, False)
            layers.append(self.osmLayer)

        self.grpTransparency.setVisible(
            self.comboDiffType.currentIndex() == TRANSPARENCY
        )

        self.sliderTransparencyNew.setValue(100)
        self.sliderTransparencyOld.setValue(100)

        self.canvas.setMapTool(self.mapTool)
        self.canvas.setLayers(layers)

        extent = self.oldLayer.extent()
        extent.combineExtentWith(self.newLayer.extent())
        extent.grow(max(extent.width(), 0.01))
        self.canvas.setExtent(extent)
        self.canvas.refresh()

    def setTransparencyNew(self):
        self.newLayer.setOpacity(self.sliderTransparencyNew.value() / 100)
        self.canvas.refresh()

    def setTransparencyOld(self):
        self.oldLayer.setOpacity(self.sliderTransparencyOld.value() / 100)
        self.canvas.refresh()

    def _geomFromGeojson(self, geojson):
        feats = QgsJsonUtils.stringToFeatureList(json.dumps(geojson))
        geom = feats[0].geometry()
        return geom

    def _createLayers(self):
        old = self.currentFeature.old
        new = self.currentFeature.new
        layername = self.currentFeature.layer
        if layername not in self.workingCopyLayers:
            self.workingCopyLayers[layername] = self.repo.workingCopyLayer(layername)
        layer = self.workingCopyLayers[layername]
        if layername not in self.workingCopyLayersIdFields:
            self.workingCopyLayersIdFields[
                layername
            ] = self.repo.workingCopyLayerIdField(layername)
        if layername not in self.workingCopyLayerCrs:
            self.workingCopyLayerCrs[layername] = self.repo.workingCopyLayerCrs(
                layername
            )
        crs = self.workingCopyLayerCrs[layername]
        idField = self.workingCopyLayersIdFields[layername]
        ref = new or old
        geomtype = ref["geometry"]["type"]
        self.oldLayer = QgsVectorLayer(geomtype + f"?crs={crs}", "old", "memory")
        self.oldLayer.dataProvider().addAttributes(layer.fields().toList())
        self.oldLayer.updateFields()
        self.newLayer = QgsVectorLayer(geomtype + f"?crs={crs}", "new", "memory")
        self.newLayer.dataProvider().addAttributes(layer.fields().toList())
        self.newLayer.updateFields()
        geoms = []
        for layer, feat in [(self.newLayer, new), (self.oldLayer, old)]:
            if bool(feat):
                geom = self._geomFromGeojson(feat)
                feature = QgsFeature(layer.fields())
                for prop in feature.fields().names():
                    if prop in new:
                        feature[prop] = feat[prop]
                    feature[idField] = self.currentFeature.fid
                feature.setGeometry(geom)
                layer.dataProvider().addFeatures([feature])
                geoms.append(geom)
            else:
                geoms.append(None)
        self._createVertexDiffLayer(geoms)
        self.btnRecoverOldVersion.setEnabled(bool(old))
        self.btnRecoverNewVersion.setEnabled(bool(new))
        self.sliderTransparencyOld.setEnabled(bool(old))
        self.sliderTransparencyNew.setEnabled(bool(new))

    def _createVertexDiffLayer(self, geoms):
        textGeometries = []
        for geom in geoms:
            if geom is not None:
                text = geom.asWkt(precision=5)
                valid = " -1234567890.,"
                text = "".join([c for c in text if c in valid])
                textGeometries.append(text.split(","))
            else:
                textGeometries.append("")
        lines = difflib.Differ().compare(textGeometries[0], textGeometries[1])
        data = []
        for line in lines:
            if line.startswith("+"):
                data.append([None, line[2:]])
            if line.startswith("-"):
                data.append([line[2:], None])
            if line.startswith(" "):
                data.append([line[2:], line[2:]])
        layername = self.currentFeature.layer
        crs = self.workingCopyLayerCrs[layername]
        self.vertexDiffLayer = QgsVectorLayer(
            f"Point?crs={crs}s&field=changetype:string", "vertexdiff", "memory"
        )
        feats = []
        for coords in data:
            coord = coords[0] or coords[1]
            feat = QgsFeature()
            x, y = coord.strip().split(" ")
            pt = QgsGeometry.fromPointXY(QgsPointXY(float(x), float(y)))
            feat.setGeometry(pt)
            if coords[0] is None:
                changetype = "A"
            elif coords[1] is None:
                changetype = "R"
            else:
                changetype = "U"
            feat.setAttributes([changetype])
            feats.append(feat)

        self.vertexDiffLayer.dataProvider().addFeatures(feats)
        self.vertexDiffLayer.loadNamedStyle(pointsStyle)
        QgsProject.instance().addMapLayer(self.vertexDiffLayer, False)

    def removeMapLayers(self):
        layers = [self.oldLayer, self.newLayer, self.osmLayer, self.vertexDiffLayer]
        for layer in layers:
            if layer is not None:
                QgsProject.instance().removeMapLayer(layer.id())
        self.oldLayer = None
        self.newLayer = None

    def recoverOldVersion(self):
        self._recoverVersion(self.oldLayer)

    def recoverNewVersion(self):
        self._recoverVersion(self.newLayer)

    def _recoverVersion(self, layer):
        new = list(layer.getFeatures())[0]
        layer = self.workingCopyLayers[self.currentFeature.layer]
        idField = self.workingCopyLayersIdFields[self.currentFeature.layer]
        with edit(layer):
            old = list(layer.getFeatures(f'"{idField}" = {self.currentFeature.fid}'))
            if old:
                layer.deleteFeature(old[0].id())
            layer.addFeature(new)
        self.repo.updateCanvas()
        self.workingLayerChanged.emit()


class FeatureItem(QTreeWidgetItem):
    def __init__(self, fid, old, new, layer):
        QTreeWidgetItem.__init__(self)
        self.setIcon(0, featureIcon)
        self.setText(0, fid)
        self.old = old
        self.new = new
        self.layer = layer
        self.fid = fid


class DiffItem(QTableWidgetItem):
    def __init__(self, value):
        self.value = value
        if value is None:
            s = ""
        elif isinstance(value, dict):
            s = value["type"]
        else:
            s = str(value)
        QTableWidgetItem.__init__(self, s)
