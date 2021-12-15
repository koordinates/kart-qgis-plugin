# Code adapted from the MapSwipe plugin
# (C) 2015 by Hirofumi Hayashi and Luiz Motta
# email: hayashi@apptec.co.jp and motta.luiz@gmail.com

from qgis.PyQt.QtCore import QRect, QLine, Qt
from qgis.PyQt.QtGui import QColor, QImage

from qgis.core import QgsMapRendererParallelJob, QgsMapSettings
from qgis.gui import QgsMapCanvasItem


class SwipeMap(QgsMapCanvasItem):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.length = 0
        self.isVertical = True
        self.setZValue(-9.0)
        self.flg = False
        self.layers = []
        self.canvas = canvas
        self.image = None

    def clear(self):
        del self.layers[:]
        self.length = -1

    def setLayer(self, layer):
        self.layers = [layer]

    def setIsVertical(self, isVertical):
        self.isVertical = isVertical

    def setLength(self, x, y):
        y = self.image.height() - y
        self.length = x if self.isVertical else y
        self.setMap()
        self.update()

    def paint(self, painter, *args):  # NEED *args for WINDOWS!
        if len(self.layers) == 0 or self.length == -1 or self.image is None:
            return

        if self.isVertical:
            h = self.image.height() - 2
            w = self.length
            line = QLine(w - 1, 0, w - 1, h - 1)
        else:
            h = self.image.height() - self.length
            w = self.image.width() - 2
            line = QLine(0, h - 1, w - 1, h - 1)

        image = self.image.copy(0, 0, int(w), int(h))
        painter.drawImage(QRect(0, 0, int(w), int(h)), image)
        painter.drawLine(line)

    def setMap(self):
        def finished():
            image = job.renderedImage()
            self.image = image
            print(image.width(), image.height())

        if len(self.layers) == 0:
            return

        settings = QgsMapSettings(self.canvas.mapSettings())
        settings.setLayers(self.layers)
        settings.setBackgroundColor(QColor(Qt.transparent))

        self.setRect(self.canvas.extent())
        job = QgsMapRendererParallelJob(settings)
        job.start()
        job.finished.connect(finished)
        job.waitForFinished()
