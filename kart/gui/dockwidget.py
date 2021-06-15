import math
import os
import csv
from datetime import date, timedelta
import matplotlib.dates as mdates
from matplotlib.backends.backend_qt5agg import FigureCanvas
from matplotlib.figure import Figure
from scipy import stats
import numpy as np

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QFileDialog, QVBoxLayout, QSizePolicy, QLabel
from qgis.PyQt.QtGui import QColor

from qgis.core import (
    QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject,
    QgsRectangle, QgsFeatureRequest, QgsSymbol, QgsRendererRange,
    QgsGraduatedSymbolRenderer, QgsApplication, Qgis, QgsVectorFileWriter,
    QgsFields, QgsStyle
)
from qgis.gui import QgsMessageBar, QgsMapToolPan
from qgis.utils import iface

from detektia.maptools import MapToolSelectPoint, MapToolDrawPolygon, MapToolDrawPolyline
from detektia.gui.range_slider import RangeSlider

pluginPath = os.path.split(os.path.dirname(__file__))[0]
WIDGET, BASE = uic.loadUiType(
    os.path.join(pluginPath, 'ui', 'dockwidget.ui'))


class DetektiaDockWidget(BASE, WIDGET):

    def __init__(self):
        super(DetektiaDockWidget, self).__init__(iface.mainWindow())
        self.setupUi(self)

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.dockWidgetContents.layout().insertWidget(0, self.bar)

        self.labelFilterMin.setText(str(self.sliderVelocity.minimum()))
        self.labelFilterMax.setText(str(self.sliderVelocity.maximum()))
        self.sliderVelocity.sliderReleased.connect(self.updateVelocityFilter)
        self.sliderVelocity.sliderMoved.connect(self.updateVelocityFilterLabel)
        self.updateVelocityFilterLabel(self.sliderVelocity.value())
        self.sliderDateFilter = RangeSlider(Qt.Horizontal)
        self.sliderDateFilter.sliderReleased.connect(self.dateFilterChanged)
        self.sliderDateFilter.sliderMoved.connect(self.updateDateFilterLabel)

        self.labelDateFilterMin = QLabel()
        self.labelDateFilterMax = QLabel()

        self.layoutDateFilter.addWidget(self.labelDateFilterMin)
        self.layoutDateFilter.addWidget(self.sliderDateFilter)
        self.layoutDateFilter.addWidget(self.labelDateFilterMax)

        self.sliderDateFilter.setVisible(False)
        self.labelDateFilter.setVisible(False)
        self.labelDateFilterMin.setVisible(False)
        self.labelDateFilterMax.setVisible(False)

        self.sliderDateFilterExport = RangeSlider(Qt.Horizontal)
        self.sliderDateFilterExport.activeRangeChanged.connect(self.dateFilterExportChanged)
        self.layoutDateFilterExport.addWidget(self.sliderDateFilterExport)

        self.mapToolPoint = MapToolSelectPoint(iface.mapCanvas())
        self.mapToolPoint.canvasClicked.connect(self.updatePoint)
        self.mapToolPolygon = MapToolDrawPolygon(iface.mapCanvas())
        self.mapToolPolygon.polygonSelected.connect(self.updatePolygon)
        self.mapToolProfileLine = MapToolDrawPolyline(iface.mapCanvas(), int(self.txtWidth.text()))
        self.mapToolProfileLine.polylineSelected.connect(self.updateProfile)

        self.mapToolDefault = QgsMapToolPan(iface.mapCanvas())

        self.btnAddLayer.clicked.connect(self.loadCsv)
        self.btnAddLayer.setIcon(QgsApplication.getThemeIcon('/mActionFileOpen.svg'),)
        self.btnSelectPoint.clicked.connect(self.setSelectTool)
        self.btnDrawPolygon.clicked.connect(self.setDrawPolygonTool)
        self.btnDrawProfileLine.clicked.connect(self.setDrawProfileLineTool)
        self.btnRemovePolygon.clicked.connect(self.removePolygon)
        self.btnRemoveProfile.clicked.connect(self.removeProfile)
        self.btnExport.clicked.connect(self.export)
        self.btnOutputFilename.clicked.connect(self.selectOutputFilename)

        self.txtWidth.textChanged.connect(self.widthChanged)

        self.comboBox.currentIndexChanged.connect(self.datasetSelected)

        iface.mapCanvas().mapToolSet.connect(self._mapToolSet)
        iface.mapCanvas().extentsChanged.connect(self.extentsChanged)

        self.layers = {}
        self.currentLayer = None
        self.currentPoint = None
        self.currentPolygon = None
        self.currentPolyline = None
        self.currentProfilePolygon = None

        self.pointPlotCanvas = FigureCanvas(Figure(figsize=(5, 3)))
        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.pointPlotCanvas)
        self.widgetPointInfoPlot.setLayout(layout)
        self.widgetPointInfoPlot.setVisible(False)
        self.labelPointPlotFit.setVisible(False)

        self.viewPlotCanvas = FigureCanvas(Figure(figsize=(5, 3)))
        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.viewPlotCanvas)
        self.widgetViewInfoPlot.setLayout(layout)
        self.widgetViewInfoPlot.setVisible(False)
        self.labelViewInfo.setVisible(False)

        self.areaPlotCanvas = FigureCanvas(Figure(figsize=(5, 3)))
        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.areaPlotCanvas)
        self.widgetPolygonInfoPlot.setLayout(layout)
        self.widgetPolygonInfoPlot.setVisible(False)
        self.labelPolygonSummary.setVisible(False)

        self.profilePlotCanvas = FigureCanvas(Figure(figsize=(5, 3)))
        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.addWidget(self.profilePlotCanvas)
        self.widgetProfilePlot.setLayout(layout)
        self.widgetProfilePlot.setVisible(False)

    def extentsChanged(self):
        self.updateViewInfoPlot()

    def updateDateFilterLabel(self):
        daysMin = self.sliderDateFilter.low()
        daysMax = self.sliderDateFilter.high()
        startDate = self._dateFromDays(daysMin)
        endDate = self._dateFromDays(daysMax)
        self.labelDateFilter.setText(f"Filter by date: {startDate} / {endDate}")

    def dateFilterChanged(self):
        self.updatePointInfoPlot()

    def dateFilterExportChanged(self, daysMin, daysMax):
        startDate = self._dateFromDays(daysMin)
        endDate = self._dateFromDays(daysMax)
        self.labelDateFilterExport.setText(f"Filter by date: {startDate} / {endDate}")

    def datasetSelected(self):
        self.currentLayer = None
        for layer in QgsProject.instance().mapLayers().values():
            if layer.id() == self.comboBox.currentData():
                self.currentLayer = layer
                break
        if self.currentLayer is not None:
            self.updateVelocityFilter()
            fields = self.currentLayer.fields()
            minDate = int(fields.at(1).name())
            maxDate = int(fields.at(len(fields) - 1).name())
            self.sliderDateFilter.blockSignals(True)
            self.sliderDateFilter.setMinimum(minDate)
            self.sliderDateFilter.setMaximum(maxDate)
            self.sliderDateFilter.setHigh(maxDate)
            self.sliderDateFilter.setLow(minDate)
            self.sliderDateFilter.blockSignals(False)
            self.dateFilterChanged()
            self.sliderDateFilterExport.blockSignals(True)
            self.sliderDateFilterExport.setMinimum(minDate)
            self.sliderDateFilterExport.setMaximum(maxDate)
            self.sliderDateFilterExport.setHigh(maxDate)
            self.sliderDateFilterExport.setLow(minDate)
            self.sliderDateFilterExport.blockSignals(False)
            self.dateFilterExportChanged(minDate, maxDate)
            self.sliderDateFilter.setVisible(False)
            self.labelDateFilter.setVisible(False)
            self.labelDateFilterMin.setVisible(False)
            self.labelDateFilterMax.setVisible(False)
            self.widgetPointInfoPlot.setVisible(False)
            self.labelPointPlotFit.setVisible(False)

            self.widgetMain.setVisible(True)
        else:
            self.widgetMain.setVisible(False)

        self.updateViewInfoPlot()
        self.updateProfilePlot()
        self.updatePolygonInfoPlot()

    def updateVelocityFilterLabel(self, v):
        self.labelVelocityFilter.setText(f"Filter by velocity (mm/year) : {v}")

    def updateVelocityFilter(self):
        vmax = self.sliderVelocity.value()
        if self.currentLayer is None:
            return
        self.currentLayer.setSubsetString(f'"vel" < {vmax}')
        self.updateViewInfoPlot()

    def _isDetektiaLayer(self, layer):
        try:
            fields = [f.name() for f in layer.fields().toList()]
            return fields[0] == "vel" and all([f.isdigit() for f in fields[1:]])
        except:
            return False

    def _layersAdded(self):
        currentLayers = [self.comboBox.itemData(i) for i in range(self.comboBox.count())]
        for layer in QgsProject.instance().mapLayers().values():
            if self._isDetektiaLayer(layer) and layer.id() not in currentLayers:
                self.comboBox.addItem(layer.name(), layer.id())

    def _layersRemoved(self):
        layerIds = [layer.id() for layer in QgsProject.instance().mapLayers().values()]
        for i in range(self.comboBox.count()):
            layerId = self.comboBox.itemData(i - self.comboBox.count())
            if layerId not in layerIds:
                self.comboBox.removeItem(i)

    def updateTabWidget(self):
        pass

    def removePolygon(self):
        self.mapToolPolygon.clear()
        self.updatePolygon(None)

    def removeProfile(self):
        self.mapToolProfileLine.clear()
        self.updateProfile(None, None)

    def updatePolygon(self, polygon):
        self.currentPolygon = polygon
        self.updatePolygonInfoPlot()

    def updateProfile(self, polygon, polyline):
        self.currentProfilePolygon = polygon
        self.currentPolyline = polyline
        self.updateProfilePlot()

    def updatePoint(self, point, button):
        if self.currentLayer is None:
            return
        bbox = QgsRectangle(point, point)
        bbox.grow(0.0001)
        points = list(self.currentLayer.getFeatures(QgsFeatureRequest().setFilterRect(bbox)))
        if points:
            self.currentPoint = points[0]
            self.updatePointInfoPlot()

    def _dateFromDays(self, days):
        zero = date(1, 1, 1)
        return zero + timedelta(days=days)

    def widthChanged(self):
        try:
            width = float(self.txtWidth.text())
        except:
            self.bar.pushMessage("", "Wrong buffer width value", level=Qgis.Warning, duration=5)
            self.btnDrawProfileLine.setEnabled(False)
            return
        self.btnDrawProfileLine.setEnabled(True)
        self.mapToolProfileLine.setWidth(width)

    def updateProfilePlot(self):
        if self.currentPolyline is None or self.currentLayer is None:
            self.widgetProfilePlot.setVisible(False)
            return
        points = self.currentLayer.getFeatures(QgsFeatureRequest().setFilterRect(
                                               self.currentProfilePolygon.boundingBox()))
        first = self.currentPolyline.vertexAt(0)
        transformLayer = QgsCoordinateTransform(self.currentLayer.crs(),
                                                QgsCoordinateReferenceSystem("EPSG:3857"),
                                                QgsProject.instance())
        transformCanvas = QgsCoordinateTransform(iface.mapCanvas().mapSettings().destinationCrs(),
                                                 QgsCoordinateReferenceSystem("EPSG:3857"),
                                                 QgsProject.instance())
        firstPoint = transformCanvas.transform(QgsPointXY(first))
        polygon = QgsGeometry(self.currentProfilePolygon)
        polygon.transform(transformCanvas)
        values = []
        for point in points:
            point3857 = point.geometry()
            point3857.transform(transformLayer)
            if polygon.contains(point3857):
                dist = point3857.distance(QgsGeometry.fromPointXY(firstPoint))
                values.append((dist, float(point["vel"])))
        values.sort(key=lambda x: x[0])
        if values:
            canvas = self.profilePlotCanvas
            canvas.figure.clear()
            ax = canvas.figure.subplots()
            ax.clear()

            ax.plot([v[0] for v in values], [v[1] for v in values])
            ax.grid()
            ax.autoscale(True)
            canvas.draw()
            self.widgetProfilePlot.setVisible(True)
        else:
            self.widgetProfilePlot.setVisible(False)

    def updateViewInfoPlot(self):
        if self.currentLayer is not None:
            bbox = iface.mapCanvas().extent()
            transform = QgsCoordinateTransform(iface.mapCanvas().mapSettings().destinationCrs(),
                                               self.currentLayer.crs(),
                                               QgsProject.instance())
            bboxTransformed = transform.transform(bbox)
            points = self.currentLayer.getFeatures(QgsFeatureRequest().setFilterRect(bboxTransformed))
            values = [float(point[0]) for point in points]
            if values:
                canvas = self.viewPlotCanvas
                canvas.figure.clear()
                ax = canvas.figure.subplots()
                ax.clear()
                ax.set_ylabel("")
                ax.set_xlabel("Velocity (mm/yr)")
                if values:
                    ax.hist(values, bins=20)
                    canvas.draw()

                s = f'''
                    <h3>Velocity metric for the {len(values)} points shown on screen:</h3>
                    <table border=1 cellspacing=0 cellpadding=5 width="100%" >
                    <tr><td>MIN</td><td>{min(values):.3f}</td></tr>
                    <tr><td>MAX/td><td>{max(values):.3f}</td></tr>
                    <tr><td>P05</td><td>{np.percentile(values, 5):.3f}</td></tr>
                    <tr><td>P95</td><td>{np.percentile(values, 95):.3f}</td></tr>
                    <tr><td>MEAN</td><td>{np.mean(values):.3f}</td></tr>
                    </table>
                '''
                canvas.figure.tight_layout()
                self.labelViewInfo.setText(s)
                self.widgetViewInfoPlot.setVisible(True)
            else:
                self.widgetViewInfoPlot.setVisible(False)
                self.labelViewInfo.setText("No points shown on screen")
            self.labelViewInfo.setVisible(True)
        else:
            self.labelViewInfo.setVisible(False)

    def updatePolygonInfoPlot(self):
        values = []
        if self.currentLayer is not None and self.currentPolygon is not None:
            transform = QgsCoordinateTransform(iface.mapCanvas().mapSettings().destinationCrs(),
                                               self.currentLayer.crs(),
                                               QgsProject.instance())
            bbox = transform.transform(self.currentPolygon.boundingBox())
            points = self.currentLayer.getFeatures(QgsFeatureRequest().setFilterRect(bbox))
            for point in points:
                if self.currentPolygon.contains(point.geometry()):
                    values.append(float(point[0]))
            if values:
                canvas = self.areaPlotCanvas
                canvas.figure.clear()
                ax = canvas.figure.subplots()
                ax.clear()
                ax.set_ylabel("")
                ax.set_xlabel("Velocity (mm/yr)")
                if values:
                    ax.hist(values, bins=20)
                    canvas.draw()

                s = f'''<h3>Velocity metric for the {len(values)} points in the polygon:</h3>
                    <table border=1 cellspacing=0 cellpadding=5 width="100%">
                    <tr><td>MIN</td><td>{min(values):.3f}</td></tr>
                    <tr><td>MAX</td><td>{max(values):.3f}</td></tr>
                    <tr><td>P05</td><td>{np.percentile(values, 5):.3f}</td></tr>
                    <tr><td>P95</td><td>{np.percentile(values, 95):.3f}</td></tr>
                    <tr><td>MEAN</td><td>{np.mean(values):.3f}</td></tr>
                    </table>
                '''
                canvas.figure.tight_layout()
                self.labelPolygonSummary.setText(s)
                self.labelPolygonSummary.setVisible(True)
                self.widgetPolygonInfoPlot.setVisible(True)
            else:
                self.widgetPolygonInfoPlot.setVisible(False)
                self.labelPolygonSummary.setText("No points in current polygon")
        else:
            self.widgetPolygonInfoPlot.setVisible(False)
            self.labelPolygonSummary.setVisible(False)

    def updatePointInfoPlot(self):
        if self.currentPoint is None:
            return
        self.widgetPointInfoPlot.setVisible(True)
        self.labelPointPlotFit.setVisible(True)
        self.sliderDateFilter.setVisible(True)
        self.labelDateFilter.setVisible(True)
        self.labelDateFilterMin.setVisible(True)
        self.labelDateFilterMax.setVisible(True)
        point = self.currentPoint
        daysMin = self.sliderDateFilter.low()
        daysMax = self.sliderDateFilter.high()
        startDate = self._dateFromDays(daysMin)
        endDate = self._dateFromDays(daysMax)
        self.labelDateFilterMin.setText(str(startDate))
        self.labelDateFilterMax.setText(str(endDate))
        self.updateDateFilterLabel()
        geom = point.geometry().asPoint()
        self.labelSelectedPoint.setText(f"Selected point: #{point.id()} ({geom.x()}, {geom.y()}) Velocity = {point[2]}")
        values = [float(point[i]) for i in range(1, len(self.currentLayer.fields()))]

        canvas = self.pointPlotCanvas
        canvas.figure.clear()
        ax = canvas.figure.subplots()
        ax.clear()

        ax.axvline(x=startDate, color='r', linestyle='--')
        ax.axvline(x=endDate, color='r', linestyle='--')

        dates = []
        alldays = []
        x = []
        y = []
        for i in range(1, len(self.currentLayer.fields())):
            days = int(self.currentLayer.fields().at(i).name())
            alldays.append(days)
            dates.append(self._dateFromDays(days))
            if days > daysMin and days < daysMax:
                x.append(days)
                y.append(float(point[i]))

        ax.plot(dates, values)
        ax.plot(dates, values, "bo")

        slope, intercept, r, p, err = stats.linregress(x, y)
        ax.plot(alldays, [slope * v + intercept for v in alldays], color='r', linestyle='--')

        self.labelPointPlotFit.setText(f"The slope of the linear regression is {slope:.3f} mm/yr, with a R2 of {r**2:.3f}")

        ax.grid()
        ax.autoscale(True)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=100))
        canvas.figure.autofmt_xdate()

        canvas.figure.tight_layout()
        canvas.draw()

    def export(self):
        if self.currentLayer is None:
            return

        filename = self.txtOutputFilename.text()
        if not os.path.exists(os.path.dirname(filename)):
            self.bar.pushMessage("", "Wrong folder for output filename", Qgis.Warning)
            return

        minDays = self.sliderDateFilterExport.low()
        maxDays = self.sliderDateFilterExport.high()
        fieldMin = 0
        fieldMax = 0

        fieldList = self.currentLayer.fields().toList()[1:]
        for field in fieldList:
            days = int(field.name())
            if days < minDays:
                fieldMin = days
            if days < maxDays:
                fieldMax = days

        fields = QgsFields()
        fields.append(QgsField("delta", QVariant.Double))
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        writer = QgsVectorFileWriter.create(filename, fields, self.currentLayer.wkbType(),
                                            self.currentLayer.crs(),
                                            QgsProject.instance().transformContext(),
                                            options)
        del writer
        layer = QgsVectorLayer(filename, "")
        layer.startEditing()
        for feature in self.currentLayer.getFeatures():
            newFeature = QgsFeature(fields)
            newFeature.setGeometry(feature.geometry())
            delta = feature[str(fieldMax)] - feature[str(fieldMin)]
            newFeature["delta"] = delta
            layer.addFeature(newFeature)
        layer.commitChanges()
        QgsProject.instance().addMapLayer(layer)
        self.bar.pushMessage("", "Layer correctly exported", Qgis.Success)

    def _mapToolSet(self, new, old):
        if not isinstance(new, MapToolSelectPoint):
            self.btnSelectPoint.setChecked(False)
        if not isinstance(new, MapToolDrawPolygon):
            self.btnDrawPolygon.setChecked(False)
        if not isinstance(new, MapToolDrawPolyline):
            self.btnDrawProfileLine.setChecked(False)

    def setSelectTool(self):
        if self.btnSelectPoint.isChecked():
            iface.mapCanvas().setMapTool(self.mapToolPoint)
        else:
            iface.mapCanvas().setMapTool(self.mapToolDefault)

    def setDrawPolygonTool(self):
        if self.btnDrawPolygon.isChecked():
            iface.mapCanvas().setMapTool(self.mapToolPolygon)
        else:
            iface.mapCanvas().setMapTool(self.mapToolDefault)

    def setDrawProfileLineTool(self):
        print(self.btnDrawProfileLine.isChecked())
        if self.btnDrawProfileLine.isChecked():
            iface.mapCanvas().setMapTool(self.mapToolProfileLine)
        else:
            print(self.mapToolDefault)
            iface.mapCanvas().setMapTool(self.mapToolDefault)

    def loadCsv(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select Filename", "", "*.csv")
        if filename:
            with open(filename) as file:
                reader = csv.reader(file, delimiter=',')
                layer = QgsVectorLayer("Point", os.path.basename(filename), "memory")
                layer.startEditing()
                layer.addAttribute(QgsField("vel", QVariant.Double))
                for i, row in enumerate(reader):
                    if i == 1:
                        for d in row[3:]:
                            layer.addAttribute(QgsField(str(d), QVariant.Double))
                        layer.updateFields()
                    elif i > 1:
                        feature = QgsFeature(layer.fields())
                        geometry = QgsGeometry.fromPointXY(QgsPointXY(float(row[0]), float(row[1])))
                        feature.setGeometry(geometry)
                        feature["vel"] = row[2]
                        for field, d in enumerate(row[3:]):
                            feature[field + 1] = d
                        layer.addFeature(feature)
                layer.commitChanges()

            QgsProject.instance().addMapLayer(layer)
            self.setStyle(layer)
            iface.mapCanvas().setExtent(layer.extent())
            self.comboBox.setCurrentIndex(self.comboBox.findData(layer.id()))

    def selectOutputFilename(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Select Filename", "", "*.shp")
        if filename:
            self.txtOutputFilename.setText(filename)

    def setStyle(self, layer):
        values = [float(f["vel"]) for f in layer.getFeatures()]
        classes = []
        classRange = max([max(values), abs(min(values))]) / 5
        ramp = QgsStyle.defaultStyle().colorRamp("Spectral")
        for i in range(5):
            classMax = (5 - i) * classRange
            classMin = (4 - i) * classRange
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(ramp.color(1 -  i / 10))
            symbol.setOpacity(1)
            rendererRange = QgsRendererRange(classMin, classMax, symbol, f"{classMin} -{classMax}")
            classes.append(rendererRange)

        for i in range(5):
            classMin = - (i + 1) * classRange
            classMax = - i * classRange
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(ramp.color(.5 - (i + 1) / 10))
            symbol.setOpacity(1)
            rendererRange = QgsRendererRange(classMin, classMax, symbol, f"{classMin} -{classMax}")
            classes.append(rendererRange)

        renderer = QgsGraduatedSymbolRenderer('', classes)
        method = QgsApplication.classificationMethodRegistry().method("EqualInterval")
        renderer.setClassificationMethod(method)
        renderer.setClassAttribute('vel')

        layer.setRenderer(renderer)

    def closeEvent(self, evt):
        return
        if self.marker is not None:
            self.canvas.scene().removeItem(self.marker)
            self.marker = None
