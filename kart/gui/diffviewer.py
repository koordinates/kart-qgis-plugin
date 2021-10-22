# -*- coding: utf-8 -*-

import os
import sys
import json

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
    QgsVectorLayer,
    QgsJsonUtils,
    QgsMarkerSymbol,
    QgsLineSymbol,
    QgsFillSymbol,
)

from qgis.core import Qgis
from qgis.gui import QgsMapCanvas, QgsMessageBar

ADDED, MODIFIED, REMOVED, UNCHANGED = 0, 1, 2, 3

pluginPath = os.path.split(os.path.dirname(__file__))[0]


def icon(f):
    return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), "img", f))


layerIcon = icon("layer_group.svg")
featureIcon = icon("geometry.png")
addedIcon = icon("add.png")
removedIcon = icon("remove.png")
modifiedIcon = icon("edit.png")

sys.path.append(os.path.dirname(__file__))
pluginPath = os.path.split(os.path.dirname(__file__))[0]
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
        self.currentFeature = None
        self.workingCopyLayers = {}

        self.setupUi(self)

        self.setWindowFlags(self.windowFlags() | Qt.WindowSystemMenuHint)

        self.canvas = QgsMapCanvas(self.canvasWidget)
        tabLayout = QVBoxLayout()
        tabLayout.setMargin(0)
        tabLayout.addWidget(self.canvas)
        self.canvasWidget.setLayout(tabLayout)

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
            # self.attributesTable.setRowCount(0)
            self.attributesTable.setVisible(False)
            self.canvasWidget.setVisible(False)
            return
        else:
            self.attributesTable.setVisible(True)
            self.canvasWidget.setVisible(True)
            self.currentFeature = current
            self.fillAttributesDiff()
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
        self.removeMapLayers()
        self._createLayers()
        QgsProject.instance().addMapLayer(self.newLayer, False)
        QgsProject.instance().addMapLayer(self.oldLayer, False)
        self.canvas.setLayers([self.oldLayer, self.newLayer])
        extent = self.oldLayer.extent()
        extent.combineExtentWith(self.newLayer.extent())
        extent.grow(max(extent.width(), 0.01))
        self.canvas.setExtent(extent)
        self.canvas.refresh()

    def _geom_from_geojson(self, geojson):
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
        ref = new or old
        geomtype = ref["geometry"]["type"]
        self.oldLayer = QgsVectorLayer(geomtype + "?crs=epsg:4326", "old", "memory")
        self.oldLayer.dataProvider().addAttributes(layer.fields().toList())
        self.oldLayer.updateFields()
        geomclass = {
            "Point": QgsMarkerSymbol,
            "Line": QgsLineSymbol,
            "Polygon": QgsFillSymbol,
        }
        symbol = geomclass.get(geomtype, QgsFillSymbol).createSimple(
            {"color": "255,0,0,100"}
        )
        self.oldLayer.renderer().setSymbol(symbol)
        self.newLayer = QgsVectorLayer(geomtype + "?crs=epsg:4326", "new", "memory")
        self.newLayer.dataProvider().addAttributes(layer.fields().toList())
        self.newLayer.updateFields()
        symbol = geomclass.get(geomtype, QgsFillSymbol).createSimple(
            {"color": "0,255,0,100"}
        )
        self.newLayer.renderer().setSymbol(symbol)
        if bool(old):
            geom = self._geom_from_geojson(old)
            feature = QgsFeature(self.oldLayer.fields())
            for prop in feature.fields().names():
                if prop in old:
                    feature[prop] = old[prop]
                feature["fid"] = self.currentFeature.fid
            feature.setGeometry(geom)
            self.oldLayer.dataProvider().addFeatures([feature])
        if bool(new):
            geom = self._geom_from_geojson(new)
            feature = QgsFeature(self.newLayer.fields())
            for prop in feature.fields().names():
                if prop in new:
                    feature[prop] = new[prop]
                feature["fid"] = self.currentFeature.fid
            feature.setGeometry(geom)
            self.newLayer.dataProvider().addFeatures([feature])
        self.btnRecoverOldVersion.setEnabled(bool(old))
        self.btnRecoverNewVersion.setEnabled(bool(new))

    def removeMapLayers(self):
        layers = list(self.workingCopyLayers.values()) + [self.oldLayer, self.newLayer]
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
        with edit(layer):
            old = list(layer.getFeatures(f'"fid" = {self.currentFeature.fid}'))
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
