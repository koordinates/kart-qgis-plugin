import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QMenu,
    QAction,
)
from qgis.PyQt.QtGui import QCursor

from qgis.utils import iface
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsRectangle,
    QgsReferencedRectangle,
)

from processing.gui.ExtentSelectionPanel import LayerSelectionDialog
from processing.gui.RectangleMapTool import RectangleMapTool


WIDGET, BASE = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "extentselectionpanel.ui")
)


class ExtentSelectionPanel(BASE, WIDGET):
    def __init__(self, dialog):
        super(ExtentSelectionPanel, self).__init__(dialog)
        self.setupUi(self)

        self.crsSelector.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        self.dialog = dialog

        self.btnSetFrom.clicked.connect(self.selectExtent)

        canvas = iface.mapCanvas()
        self.prevMapTool = canvas.mapTool()
        self.tool = RectangleMapTool(canvas)
        self.tool.rectangleCreated.connect(self.updateExtent)

    def selectExtent(self):
        popupmenu = QMenu()
        useCanvasExtentAction = QAction("Use Canvas Extent", self.btnSetFrom)
        useLayerExtentAction = QAction("Use Layer Extent…", self.btnSetFrom)
        selectOnCanvasAction = QAction("Select Extent on Canvas", self.btnSetFrom)

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
        self.setValueFromRect(
            QgsReferencedRectangle(
                iface.mapCanvas().extent(),
                iface.mapCanvas().mapSettings().destinationCrs(),
            )
        )

    def selectOnCanvas(self):
        canvas = iface.mapCanvas()
        canvas.setMapTool(self.tool)
        self.dialog.showMinimized()

    def updateExtent(self):
        r = self.tool.rectangle()
        self.setValueFromRect(r)
        self.tool.reset()
        canvas = iface.mapCanvas()
        canvas.setMapTool(self.prevMapTool)
        self.dialog.showNormal()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def setValueFromRect(self, r):
        self.txtNorth.setText(str(r.yMaximum()))
        self.txtSouth.setText(str(r.yMinimum()))
        self.txtEast.setText(str(r.xMaximum()))
        self.txtWest.setText(str(r.xMinimum()))
        try:
            crs = r.crs()
        except Exception:
            crs = QgsProject.instance().crs()
        self.crsSelector.setCrs(crs)

    def getExtent(self):
        try:
            coords = [
                float(self.txtWest.text()),
                float(self.txtSouth.text()),
                float(self.txtEast.text()),
                float(self.txtNorth.text()),
            ]
        except ValueError:
            return None
        rect = QgsRectangle(coords[0], coords[1], coords[2], coords[3])
        return QgsReferencedRectangle(rect, self.crsSelector.crs())
