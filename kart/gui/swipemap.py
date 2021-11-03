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

    def setLayers(self, layers):
        for item in layers:
            self.layers.append(item)

    def setIsVertical(self, isVertical):
        self.isVertical = isVertical

    def setLength(self, x, y):
        y = self.boundingRect().height() - y
        self.length = x if self.isVertical else y
        self.update()

    def paint(self, painter, *args):  # NEED *args for WINDOWS!
        if len(self.layers) == 0 or self.length == -1:
            return

        if self.isVertical:
            h = self.boundingRect().height() - 2
            w = self.length
            line = QLine(w - 1, 0, w - 1, h - 1)
        else:
            h = self.boundingRect().height() - self.length
            w = self.boundingRect().width() - 2
            line = QLine(0, h - 1, w - 1, h - 1)

        image = self.image.copy(0, 0, w, h)
        painter.drawImage(QRect(0, 0, w, h), image)
        painter.drawLine(line)

    def setMap(self):
        def finished():
            # https://qgis.org/api/2.18/qgsmapcanvasmap_8cpp_source.html
            # setContent()
            image = job.renderedImage()
            if bool(self.canvas.property("retro")):
                image = image.scaled(image.width() / 3, image.height() / 3)
                image = image.convertToFormat(
                    QImage.Format_Indexed8, Qt.OrderedDither | Qt.OrderedAlphaDither
                )
            self.image = image

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
