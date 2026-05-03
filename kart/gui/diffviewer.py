# -*- coding: utf-8 -*-

import json
import os

from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsFeature,
    QgsGeometry,
    QgsJsonUtils,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRendererCategory,
    QgsSingleSymbolRenderer,
    QgsSymbol,
    QgsVectorLayer,
    QgsWkbTypes,
    edit,
)
from qgis.gui import QgsMapCanvas, QgsMapToolPan, QgsMessageBar
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (
    QDialog,
    QHeaderView,
    QSizePolicy,
    QTableWidgetItem,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
)
from qgis.utils import iface

from kart.gui import icons
from kart.utils import tr

from .mapswipetool import MapSwipeTool

ADDED, MODIFIED, REMOVED, UNCHANGED = 0, 1, 2, 3

PROJECT_LAYERS = 0
OSM_BASEMAP = 1
NO_LAYERS = 2

TRANSPARENCY = 0
SWIPE = 1
VERTEX_DIFF = 2

TAB_ATTRIBUTES = 0
TAB_GEOMETRY = 1

# Diff change type colors
COLOR_ADDED = QColor(120, 200, 120)  # green
COLOR_REMOVED = QColor(230, 120, 120)  # red
COLOR_MODIFIED = QColor(255, 190, 100)  # orange
COLOR_UNCHANGED = QColor(255, 255, 255)  # white

pluginPath = os.path.split(os.path.dirname(__file__))[0]

WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), "diffviewerwidget.ui"))


class DiffViewerWidget(WIDGET, BASE):
    workingLayerChanged = pyqtSignal()

    def __init__(self, diff, repo, showRecoverNewButton):
        super(DiffViewerWidget, self).__init__()
        self.diff = diff
        self.repo = repo
        self.oldLayer = None
        self.newLayer = None
        self.osmLayer = None
        self.showRecoverNewButton = showRecoverNewButton
        self.layerDiffLayers = {}
        self.currentFeatureItem = None
        self.currentDatasetItem = None
        self.workingCopyLayers = {}
        self.workingCopyLayersIdFields = {}
        self.workingCopyLayerCrs = {}

        self.mostRecentTabIndex = None

        self.setupUi(self)

        self.retranslateUi()

        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowSystemMenuHint)

        self.canvas = QgsMapCanvas(self.canvasWidget)
        self.canvas.setCanvasColor(Qt.GlobalColor.white)
        self.canvas.enableAntiAliasing(True)
        tabLayout = QVBoxLayout()
        tabLayout.setMargin(0)
        tabLayout.addWidget(self.canvas)
        self.canvasWidget.setLayout(tabLayout)
        self.tabWidget.tabBarClicked.connect(
            lambda index: setattr(self, "mostRecentTabIndex", index)
        )
        self.sliderTransparency.setValue(50)

        self.sliderTransparency.valueChanged.connect(self.setTransparency)
        self.comboDiffType.currentIndexChanged.connect(self.fillCanvas)
        self.comboAdditionalLayers.currentIndexChanged.connect(self.fillCanvas)
        self.btnRecoverOldVersion.clicked.connect(self.recoverOldVersion)
        self.btnRecoverNewVersion.clicked.connect(self.recoverNewVersion)
        self.featuresTree.currentItemChanged.connect(self.treeItemChanged)
        self.featuresTree.header().hide()

        self.featuresTree.header().setStretchLastSection(True)

        # Dispatchers initialized once to avoid re-allocation on every fillCanvas call.
        self._baseLayerDispatchers = {
            PROJECT_LAYERS: self._baseLayersProject,
            OSM_BASEMAP: self._baseLayersOsm,
            NO_LAYERS: self._baseLayersNone,
        }
        self._diffModeDispatchers = {
            TRANSPARENCY: TransparencyMode(self),
            SWIPE: SwipeMode(self),
            VERTEX_DIFF: VertexDiffMode(self),
        }

        self.fillTree()

        self.selectFirstChangedFeature()

    # Lifecycle
    def treeItemChanged(self, current, previous):
        self.canvasWidget.setVisible(True)
        self.widgetDiffConfig.setVisible(True)
        self.tabWidget.setTabEnabled(TAB_GEOMETRY, True)
        self.tabWidget.setTabEnabled(TAB_ATTRIBUTES, True)
        self.tabWidget.setCurrentIndex(self.mostRecentTabIndex or TAB_ATTRIBUTES)
        if isinstance(current, FeatureItem):
            self.currentFeatureItem = current
            self.currentDatasetItem = None
            self.fillAttributesDiff()
            self.removeMapLayers()
            self.attributesTable.setVisible(True)
            self.btnRecoverNewVersion.setVisible(True and self.showRecoverNewButton)
            self.btnRecoverOldVersion.setVisible(True)
            self._createLayers()
            if self._hasGeometry(current):
                self.comboDiffType.view().setRowHidden(VERTEX_DIFF, False)
                self.fillCanvas()
            else:
                self.tabWidget.setTabEnabled(TAB_GEOMETRY, False)
        elif isinstance(current, DatasetItem):
            self.currentFeatureItem = None
            self.currentDatasetItem = current
            self.removeMapLayers()
            self.tabWidget.setTabEnabled(TAB_ATTRIBUTES, False)
            self.attributesTable.setVisible(False)
            self.btnRecoverNewVersion.setVisible(False)
            self.btnRecoverOldVersion.setVisible(False)
            if self._hasGeometry(current):
                self.comboDiffType.view().setRowHidden(VERTEX_DIFF, True)
                self._createLayers()
                self.fillCanvas()
            else:
                self.tabWidget.setTabEnabled(TAB_GEOMETRY, False)
        else:
            self.tabWidget.setTabEnabled(TAB_GEOMETRY, False)
            self.tabWidget.setTabEnabled(TAB_ATTRIBUTES, False)
            self.attributesTable.setVisible(False)
            self.grpTransparency.setVisible(False)
            self.canvasWidget.setVisible(False)
            self.widgetDiffConfig.setVisible(False)
            self.btnRecoverNewVersion.setVisible(False)
            self.btnRecoverOldVersion.setVisible(False)
        self.tabWidget.setStyleSheet(
            "QTabBar::tab::disabled {width: 0; height: 0; margin: 0; padding: 0; border: none;} "
        )

    def removeMapLayers(self):
        self._cleanupModeLayers()
        for layer in [self.oldLayer, self.newLayer, self.osmLayer]:
            if layer is not None:
                QgsProject.instance().removeMapLayer(layer.id())
        self.oldLayer = None
        self.newLayer = None
        self.osmLayer = None

    # Rendering
    def fillCanvas(self):
        self._cleanupModeLayers()
        # Hide transparency controls
        self.grpTransparency.setVisible(False)

        self.canvas.setLayers([])
        self.canvas.setDestinationCrs(self.oldLayer.crs())
        self._addToProject(self.newLayer)
        self._addToProject(self.oldLayer)
        self.mapTool = QgsMapToolPan(self.canvas)

        # Reset layer state before delegating to mode.
        self.newLayer.setOpacity(1)
        self.oldLayer.setOpacity(1)

        # Apply programmatic styles using the shared color constants.
        self._applyLayerStyle(self.newLayer, COLOR_ADDED)
        self._applyLayerStyle(self.oldLayer, COLOR_REMOVED)

        # Data layers start at the top of the stack.
        layers_data = [self.newLayer, self.oldLayer]

        # Base layers always go to the bottom.
        layers_base = self._baseLayerDispatchers[self.comboAdditionalLayers.currentIndex()]()

        # Diff mode is fully responsible for its own layer stack and map tool.
        layers_data = self._diffModeDispatchers[self.comboDiffType.currentIndex()].setup(
            layers_data
        )

        # Final stack: [top] data + [bottom] base.
        self.canvas.setMapTool(self.mapTool)
        self.canvas.setLayers(layers_data + layers_base)

        extent = self.oldLayer.extent()
        extent.combineExtentWith(self.newLayer.extent())
        d = min(extent.width(), extent.height())
        if d == 0:
            d = 1
        extent = extent.buffered(d * 0.07)
        self.canvas.setExtent(extent)
        self.canvas.refresh()

    def _applyLayerStyle(self, layer, color):
        """Apply a single-symbol renderer with the given color to a vector layer."""
        geometry_type = layer.geometryType()
        symbol = QgsSymbol.defaultSymbol(geometry_type)
        symbol.setColor(color)
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()

    def _cleanupModeLayers(self):
        """Delegate cleanup to each mode — each mode owns its temporary layers."""
        for mode in self._diffModeDispatchers.values():
            mode.cleanup()

    def _addToProject(self, layer):
        """Add a layer to the project only if not already registered."""
        if not QgsProject.instance().mapLayer(layer.id()):
            QgsProject.instance().addMapLayer(layer, False)

    # --- Base layer providers ---
    # To add a new base layer source, implement _baseLayers<Name> and
    # register it in self._baseLayerDispatchers in __init__.

    def _baseLayersProject(self):
        return list(iface.mapCanvas().layers())

    def _baseLayersOsm(self):
        uri = (
            "crs=EPSG:3857&type=xyz&"
            "url=https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            "&zmax=19&zmin=0"
        )
        options = QgsRasterLayer.LayerOptions()
        options.skipCrsValidation = True
        self.osmLayer = QgsRasterLayer(uri, "OSM", "wms", options)
        QgsProject.instance().addMapLayer(self.osmLayer, False)
        return [self.osmLayer]

    def _baseLayersNone(self):
        return []

    # Layer creation
    def _createLayers(self):
        if self.currentFeatureItem is not None:
            self._createFeatureDiffLayers()
        elif self.currentDatasetItem is not None:
            oldLayer, newLayer = self.layerDiffLayers[self.currentDatasetItem.dataset]
            self.oldLayer = oldLayer.clone()
            self.newLayer = newLayer.clone()

    def _createFeatureDiffLayers(self):
        old = self.currentFeatureItem.old
        new = self.currentFeatureItem.new
        dataset = self.currentFeatureItem.dataset
        if dataset not in self.workingCopyLayers:
            self.workingCopyLayers[dataset] = self.repo.workingCopyLayer(dataset)
        layer = self.workingCopyLayers[dataset]
        if dataset not in self.workingCopyLayersIdFields:
            self.workingCopyLayersIdFields[dataset] = self.repo.workingCopyLayerIdField(dataset)
        crs = self.workingCopyLayerCrs[dataset]
        idField = self.workingCopyLayersIdFields[dataset]
        ref = new or old
        refGeom = ref["geometry"]
        options = QgsVectorLayer.LayerOptions()
        options.skipCrsValidation = True
        if refGeom is not None:
            geomtype = refGeom["type"]
            self.oldLayer = QgsVectorLayer(f"{geomtype}?crs={crs}", "old", "memory", options)
            self.newLayer = QgsVectorLayer(f"{geomtype}?crs={crs}", "new", "memory", options)
        else:
            self.oldLayer = QgsVectorLayer("None", "old", "memory", options)
            self.newLayer = QgsVectorLayer("None", "new", "memory", options)

        self.oldLayer.dataProvider().addAttributes(layer.fields().toList())
        self.oldLayer.updateFields()
        self.newLayer.dataProvider().addAttributes(layer.fields().toList())
        self.newLayer.updateFields()

        for lyr, feat in [(self.newLayer, new), (self.oldLayer, old)]:
            if bool(feat):
                geom = self._geomFromGeojson(feat)
                props = feat["properties"]
                feature = QgsFeature(lyr.fields())
                for prop in feature.fields().names():
                    feature[prop] = props[prop]
                feature[idField] = self.currentFeatureItem.fid
                if geom is not None:
                    feature.setGeometry(geom)
                lyr.dataProvider().addFeatures([feature])

        currentFieldNames = set(layer.fields().names())
        oldFieldNames = set(old.get("properties", {}).keys())
        newFieldNames = set(new.get("properties", {}).keys())

        noSchemaChange = currentFieldNames == oldFieldNames == newFieldNames

        self.btnRecoverOldVersion.setEnabled(bool(old) and noSchemaChange)
        self.btnRecoverNewVersion.setEnabled(
            bool(new) and self.showRecoverNewButton and noSchemaChange
        )

    def _createVertexDiffLayer(self, geoms):
        dataset = self.currentFeatureItem.dataset
        crs = self.workingCopyLayerCrs[dataset]
        options = QgsVectorLayer.LayerOptions()
        options.skipCrsValidation = True
        vertexDiffLayer = QgsVectorLayer(
            f"Point?crs={crs}&field=changetype:string", "vertexdiff", "memory", options
        )

        def vertices(geom):
            if geom is None or geom.isEmpty():
                return set()
            return {(round(v.x(), 5), round(v.y(), 5)) for v in geom.vertices()}

        old_vertices = vertices(geoms[0])
        new_vertices = vertices(geoms[1])

        changetype_map = [
            ("A", new_vertices - old_vertices),  # added: present in new, absent in old
            ("R", old_vertices - new_vertices),  # removed: present in old, absent in new
            ("U", old_vertices & new_vertices),  # unchanged: present in both
        ]

        feats = []
        for changetype, vertex_set in changetype_map:
            for x, y in vertex_set:
                feat = QgsFeature()
                feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                feat.setAttributes([changetype])
                feats.append(feat)

        vertexDiffLayer.dataProvider().addFeatures(feats)

        # Apply categorized renderer using the shared color constants.
        marker_symbol_added = QgsSymbol.defaultSymbol(vertexDiffLayer.geometryType())
        marker_symbol_removed = QgsSymbol.defaultSymbol(vertexDiffLayer.geometryType())
        marker_symbol_unchanged = QgsSymbol.defaultSymbol(vertexDiffLayer.geometryType())

        marker_symbol_added.setColor(COLOR_ADDED)
        marker_symbol_removed.setColor(COLOR_REMOVED)
        marker_symbol_unchanged.setColor(COLOR_UNCHANGED)

        categories = [
            QgsRendererCategory("A", marker_symbol_added, tr("Added")),
            QgsRendererCategory("R", marker_symbol_removed, tr("Removed")),
            QgsRendererCategory("U", marker_symbol_unchanged, tr("Unchanged")),
        ]

        vertexDiffLayer.setRenderer(QgsCategorizedSymbolRenderer("changetype", categories))

        QgsProject.instance().addMapLayer(vertexDiffLayer, False)
        return vertexDiffLayer

    # UI
    def fillTree(self):
        self.featuresTree.clear()
        for dataset, changes in self.diff.items():
            if dataset not in self.workingCopyLayerCrs:
                self.workingCopyLayerCrs[dataset] = self.repo.workingCopyLayerCrs(dataset)
            crs = self.workingCopyLayerCrs[dataset]
            datasetItem = DatasetItem(dataset, crs is None)
            addedItem = QTreeWidgetItem()
            addedItem.setText(0, tr("Added"))
            addedItem.setIcon(0, icons.addedIcon)
            removedItem = QTreeWidgetItem()
            removedItem.setText(0, tr("Removed"))
            removedItem.setIcon(0, icons.removeIcon)
            modifiedItem = QTreeWidgetItem()
            modifiedItem.setText(0, tr("Modified"))
            modifiedItem.setIcon(0, icons.modifiedIcon)

            subItems = {"I": addedItem, "U": modifiedItem, "D": removedItem}
            changes = {feat["id"]: feat for feat in changes}
            usedids = []
            for feat in changes.values():
                # Try to parse the feature id string in the old format first
                # and if that fails try the new format. The old format is
                # the change type and numeric id, eg.
                # 'U-::49'
                # whereas the new format additionally includes the dataset name
                # and element type eg.
                # 'nz_pipelines:feature:49:U-'
                # TODO - remove support for 'old' format, requires users to have upgraded
                #  this plugin first
                is_new_id_format = False
                elementtype = None
                try:
                    changetype, featid = feat["id"].split("::")
                except ValueError:
                    _, elementtype, featid, changetype = feat["id"].split(":")
                    is_new_id_format = True
                changetype = changetype[0]
                if featid not in usedids:
                    if changetype == "I":
                        old = {}
                        new = feat
                    elif changetype == "D":
                        old = feat
                        new = {}
                    else:
                        if is_new_id_format:
                            old = changes[f"{dataset}:{elementtype}:{featid}:U-"]
                            new = changes[f"{dataset}:{elementtype}:{featid}:U+"]
                        else:
                            old = changes[f"U-::{featid}"]
                            new = changes[f"U+::{featid}"]
                    usedids.append(featid)
                    item = FeatureItem(featid, old, new, dataset)
                    subItems[changetype].addChild(item)
                if dataset not in self.layerDiffLayers:
                    ref = new or old
                    geom = ref["geometry"]
                    if geom is not None:
                        geomtype = geom["type"]
                        oldLayer = QgsVectorLayer(f"{geomtype}?crs={crs}", "old", "memory")
                        newLayer = QgsVectorLayer(f"{geomtype}?crs={crs}", "new", "memory")
                    else:
                        oldLayer = QgsVectorLayer("None", "old", "memory")
                        newLayer = QgsVectorLayer("None", "new", "memory")
                    self.layerDiffLayers[dataset] = (oldLayer, newLayer)

                if old and old["geometry"] is not None:
                    oldFeature = QgsFeature()
                    oldFeature.setGeometry(self._geomFromGeojson(old))
                    oldLayer.dataProvider().addFeatures([oldFeature])
                if new and new["geometry"] is not None:
                    newFeature = QgsFeature()
                    newFeature.setGeometry(self._geomFromGeojson(new))
                    newLayer.dataProvider().addFeatures([newFeature])
            for subItem in subItems.values():
                if subItem.childCount():
                    datasetItem.addChild(subItem)
            if datasetItem.childCount():
                self.featuresTree.addTopLevelItem(datasetItem)

        self.attributesTable.clear()
        self.attributesTable.verticalHeader().hide()
        self.attributesTable.horizontalHeader().hide()
        self.featuresTree.expandAll()

    def fillAttributesDiff(self):
        old = self.currentFeatureItem.old
        new = self.currentFeatureItem.new
        oldprops = old.get("properties", {})
        newprops = new.get("properties", {})
        self.attributesTable.clear()
        fields = []
        fields.extend(new.get("properties", {}).keys())
        fields.extend(old.get("properties", {}).keys())
        fields = list(set(fields))

        changeTypeColor = [COLOR_ADDED, COLOR_MODIFIED, COLOR_REMOVED, COLOR_UNCHANGED]
        changeTypeName = [tr("Added"), tr("Modified"), tr("Removed"), tr("Unchanged")]

        self.attributesTable.clear()
        self.attributesTable.verticalHeader().show()
        self.attributesTable.horizontalHeader().show()
        labels = fields + ["geometry"]
        self.attributesTable.setRowCount(len(labels))
        self.attributesTable.setVerticalHeaderLabels(labels)
        self.attributesTable.setHorizontalHeaderLabels(
            [tr("Old value"), tr("New value"), tr("Change type")]
        )
        for i, attrib in enumerate(fields):
            try:
                oldvalue = oldprops.get(attrib, "")
                newvalue = newprops.get(attrib, "")
                if attrib not in oldprops:
                    changeType = ADDED
                elif attrib not in newprops:
                    changeType = REMOVED
                else:
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
            newvalue = "" if new is None else new["geometry"]
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
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            width = header.sectionSize(column)
            header.resizeSection(column, width)
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)

    def setTransparency(self):
        self.newLayer.setOpacity(self.sliderTransparency.value() / 100)
        self.oldLayer.setOpacity((100 - self.sliderTransparency.value()) / 100)
        self.canvas.refresh()

    def retranslateUi(self, *args):
        """Update translations for UI elements from the .ui file"""
        super().retranslateUi(self)

        # Tab titles
        self.tabWidget.setTabText(TAB_ATTRIBUTES, tr("Attributes"))
        self.tabWidget.setTabText(TAB_GEOMETRY, tr("Geometries"))

        # Table columns
        self.attributesTable.setHorizontalHeaderLabels(
            [tr("Old Value"), tr("New Value"), tr("Change type")]
        )

        # Geometry tab labels (named widgets from diffviewerwidget.ui)
        self.label.setText(tr("Additional layers:"))
        self.label_2.setText(tr("Diff type:"))

        # Additional layers combo options
        self.comboAdditionalLayers.setItemText(PROJECT_LAYERS, tr("Project layers"))
        self.comboAdditionalLayers.setItemText(OSM_BASEMAP, tr("OSM basemap"))
        self.comboAdditionalLayers.setItemText(NO_LAYERS, tr("No additional layers"))

        # Diff type combo options
        self.comboDiffType.setItemText(TRANSPARENCY, tr("Transparency"))
        self.comboDiffType.setItemText(SWIPE, tr("Swipe"))
        self.comboDiffType.setItemText(VERTEX_DIFF, tr("Per-vertex diff"))

        # Transparency group and labels
        self.grpTransparency.setTitle(tr("Transparency"))
        self.label_3.setText(tr("Old version"))
        self.label_4.setText(tr("New version"))

        # Buttons
        self.btnRecoverOldVersion.setText(tr("Restore old version"))
        self.btnRecoverNewVersion.setText(tr("Restore new version"))

    # Recovery
    def recoverOldVersion(self):
        self._recoverVersion(self.oldLayer)

    def recoverNewVersion(self):
        self._recoverVersion(self.newLayer)

    def _recoverVersion(self, layer):
        new = list(layer.getFeatures())[0]
        layer = self.workingCopyLayers[self.currentFeatureItem.dataset]
        idField = self.workingCopyLayersIdFields[self.currentFeatureItem.dataset]
        with edit(layer):
            old = list(layer.getFeatures(f'"{idField}" = {self.currentFeatureItem.fid}'))
            if old:
                layer.deleteFeature(old[0].id())
            layer.addFeature(new)
        self.repo.updateCanvas()
        self.workingLayerChanged.emit()

    # Helpers
    def selectFirstChangedFeature(self):
        iterator = QTreeWidgetItemIterator(self.featuresTree)
        while iterator.value():
            item = iterator.value()
            if isinstance(item, FeatureItem):
                self.featuresTree.setCurrentItem(item)
                return
            iterator += 1

    def _hasGeometry(self, item):
        if isinstance(item, FeatureItem):
            old = self.currentFeatureItem.old
            new = self.currentFeatureItem.new
            ref = old or new
            return ref["geometry"] is not None
        else:
            oldLayer, newLayer = self.layerDiffLayers[item.dataset]
            return oldLayer.wkbType() != QgsWkbTypes.Type.NoGeometry

    def _geomFromGeojson(self, geojson):
        if not geojson or "geometry" not in geojson:
            return None
        feats = QgsJsonUtils.stringToFeatureList(json.dumps(geojson))
        return feats[0].geometry() if feats else None


class DiffViewerDialog(QDialog):
    def __init__(self, parent, diff, repo, showRecoverNewButton=True):
        super(QDialog, self).__init__(parent)
        self.setWindowFlags(Qt.WindowType.Window)
        layout = QVBoxLayout()
        layout.setMargin(0)
        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.bar)
        self.history = DiffViewerWidget(diff, repo, showRecoverNewButton)
        self.history.workingLayerChanged.connect(self.workingLayerChanged)
        layout.addWidget(self.history)
        self.setLayout(layout)
        self.resize(1024, 768)
        self.setWindowTitle(tr("Diff viewer"))

    def workingLayerChanged(self):
        self.bar.pushMessage(
            tr("Diff"),
            tr("Working copy has been updated"),
            Qgis.MessageLevel.Success,
            5,
        )

    def closeEvent(self, evt):
        self.history.removeMapLayers()
        evt.accept()


# Diff modes
class DiffMode:
    """
    Base contract for diff visualization modes.
    To add a new mode: subclass DiffMode, implement setup(), and register
    an instance in DiffViewerWidget._diffModeDispatchers.
    """

    def __init__(self, widget):
        self.w = widget

    def setup(self, layers_data):
        """
        Apply this mode. Receives the data layer list, returns the updated
        list. Responsible for setting self.w.mapTool and showing/hiding any
        mode-specific UI widgets. Layer state (opacity, styles) is already
        reset by fillCanvas before this method is called.
        """
        raise NotImplementedError

    def cleanup(self):
        """Remove any temporary layers created by this mode from the project."""
        pass


class TransparencyMode(DiffMode):
    def setup(self, layers_data):
        self.w.grpTransparency.setVisible(True)
        # Block signals to avoid double call to setTransparency via valueChanged.
        self.w.sliderTransparency.blockSignals(True)
        self.w.sliderTransparency.setValue(50)
        self.w.sliderTransparency.blockSignals(False)
        self.w.setTransparency()
        return layers_data


class SwipeMode(DiffMode):
    def setup(self, layers_data):
        # newLayer is always the swipe overlay (covers from left/above).
        # oldLayer is always the base (visible on right/below).
        # Consistent with transparency mode: old=right/below, new=left/above.
        self.w.mapTool = MapSwipeTool(self.w.canvas, self.w.newLayer)
        layers_data.remove(self.w.newLayer)
        return layers_data


class VertexDiffMode(DiffMode):
    def __init__(self, widget):
        super().__init__(widget)
        self._vertexDiffLayer = None
        self._vertexDiffNewOutline = None
        self._vertexDiffOldOutline = None

    def cleanup(self):
        for layer in [
            self._vertexDiffNewOutline,
            self._vertexDiffOldOutline,
            self._vertexDiffLayer,
        ]:
            if layer is not None:
                QgsProject.instance().removeMapLayer(layer.id())
        self._vertexDiffNewOutline = None
        self._vertexDiffOldOutline = None
        self._vertexDiffLayer = None

    def setup(self, layers_data):
        if self.w.currentFeatureItem:
            old = self.w.currentFeatureItem.old
            new = self.w.currentFeatureItem.new
            geoms = [
                self.w._geomFromGeojson(old) if old else None,
                self.w._geomFromGeojson(new) if new else None,
            ]
            self._vertexDiffLayer = self.w._createVertexDiffLayer(geoms)

        symbolType = type(QgsSymbol.defaultSymbol(self.w.oldLayer.geometryType()))

        outline_style = {
            "color": "0,0,0,255",
            "outline_color": "0,0,0,255",
            "style": "no",
            "outline_style": "solid",
        }

        self._vertexDiffNewOutline = self.w.newLayer.clone()
        self._vertexDiffNewOutline.setRenderer(
            QgsSingleSymbolRenderer(symbolType.createSimple(outline_style))
        )
        self._vertexDiffOldOutline = self.w.oldLayer.clone()
        self._vertexDiffOldOutline.setRenderer(
            QgsSingleSymbolRenderer(symbolType.createSimple(outline_style))
        )

        QgsProject.instance().addMapLayer(self._vertexDiffNewOutline, False)
        QgsProject.instance().addMapLayer(self._vertexDiffOldOutline, False)

        if self.w.newLayer in layers_data:
            layers_data.remove(self.w.newLayer)
        if self.w.oldLayer in layers_data:
            layers_data.remove(self.w.oldLayer)

        # Order: [top] vertex points → outlines [bottom].
        result = []
        if self._vertexDiffLayer:
            result.append(self._vertexDiffLayer)
        result.extend([self._vertexDiffNewOutline, self._vertexDiffOldOutline])
        return result


# Data model classes
class FeatureItem(QTreeWidgetItem):
    def __init__(self, fid, old, new, dataset):
        QTreeWidgetItem.__init__(self)
        self.setIcon(0, icons.featureIcon)
        self.setText(0, fid)
        self.old = old
        self.new = new
        self.dataset = dataset
        self.fid = fid


class DatasetItem(QTreeWidgetItem):
    def __init__(self, dataset, isTable):
        QTreeWidgetItem.__init__(self)
        self.dataset = dataset
        self.setIcon(0, icons.tableIcon if isTable else icons.vectorDatasetIcon)
        self.setText(0, dataset)


class DiffItem(QTableWidgetItem):
    def __init__(self, value):
        self.value = value
        if value is None:
            s = ""
        elif isinstance(value, dict):
            s = value.get("type", str(value))
        else:
            s = str(value)
        QTableWidgetItem.__init__(self, s)
