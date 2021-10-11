# Adapted from the Processing extent selection panel

import os
import warnings

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QMenu,
    QAction,
)
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtCore import pyqtSignal

from qgis.utils import iface
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsRectangle,
    QgsReferencedRectangle,
)

from processing.gui.ExtentSelectionPanel import LayerSelectionDialog
from processing.gui.RectangleMapTool import RectangleMapTool
from processing import gui


processingGuiPath = os.path.split(os.path.dirname(gui.__file__))[0]

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    WIDGET, BASE = uic.loadUiType(
        os.path.join(processingGuiPath, 'ui', 'widgetBaseSelector.ui'))


class ExtentSelectionPanel(BASE, WIDGET):
    hasChanged = pyqtSignal()

    def __init__(self, dialog):
        super(ExtentSelectionPanel, self).__init__(dialog)
        self.setupUi(self)

        self.leText.textChanged.connect(lambda: self.hasChanged.emit())

        self.dialog = dialog
        self.crs = QgsProject.instance().crs()

        self.btnSelect.clicked.connect(self.selectExtent)

        canvas = iface.mapCanvas()
        self.prevMapTool = canvas.mapTool()
        self.tool = RectangleMapTool(canvas)
        self.tool.rectangleCreated.connect(self.updateExtent)



    def selectExtent(self):
        popupmenu = QMenu()
        useCanvasExtentAction = QAction('Use Canvas Extent', self.btnSelect)
        useLayerExtentAction = QAction('Use Layer Extent…',  self.btnSelect)
        selectOnCanvasAction = QAction('Select Extent on Canvas', self.btnSelect)

        popupmenu.addAction(useCanvasExtentAction)
        popupmenu.addAction(selectOnCanvasAction)
        popupmenu.addSeparator()
        popupmenu.addAction(useLayerExtentAction)

        selectOnCanvasAction.triggered.connect(self.selectOnCanvas)
        useLayerExtentAction.triggered.connect(self.useLayerExtent)
        useCanvasExtentAction.triggered.connect(self.useCanvasExtent)

        popupmenu.exec_(QCursor.pos())


    def useLayerExtent(self):
        dlg = LayerSelectionDialog(self)
        if dlg.exec_():
            layer = dlg.selected_layer()
            self.setValueFromRect(QgsReferencedRectangle(layer.extent(), layer.crs()))

    def useCanvasExtent(self):
        self.setValueFromRect(QgsReferencedRectangle(iface.mapCanvas().extent(),
                                                     iface.mapCanvas().mapSettings().destinationCrs()))

    def selectOnCanvas(self):
        canvas = iface.mapCanvas()
        canvas.setMapTool(self.tool)
        self.dialog.showMinimized()

    def updateExtent(self):
        r = self.tool.rectangle()
        self.setValueFromRect(r)

    def setValueFromRect(self, r):
        s = '{},{},{},{}'.format(
            r.xMinimum(), r.xMaximum(), r.yMinimum(), r.yMaximum())

        try:
            self.crs = r.crs()
        except:
            self.crs = QgsProject.instance().crs()
        if self.crs.isValid():
            s += ' [' + self.crs.authid() + ']'

        self.leText.setText(s)
        self.tool.reset()
        canvas = iface.mapCanvas()
        canvas.setMapTool(self.prevMapTool)
        self.dialog.showNormal()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def getExtent(self):
        if self.leText.text().strip() != '':
            extent = self.leText.text()
            tokens = extent[:extent.find("[")].split(",")
            if len(tokens) !=4:
                return None
            try:
                coords = [float(v) for v in tokens]
            except ValueError:
                return None
            rect = QgsRectangle(coords[0], coords[2], coords[1], coords[3])
            if "[" in extent:
                authid = extent[extent.find("[") + 1:extent.find("]")]
                print(authid)
                crs = QgsCoordinateReferenceSystem(authid)
                if not crs.isValid():
                    return None
            else:
                crs = QgsProject.instance().crs()
            return QgsReferencedRectangle(rect, crs)
        else:
            return None

    def setExtentFromString(self, s):
        self.leText.setText(s)