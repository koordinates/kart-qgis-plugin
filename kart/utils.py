import os

from qgis.core import QgsProject


def layerFromSource(path):
    path = os.path.abspath(path)
    for layer in QgsProject.instance().mapLayers().values():
        if os.path.abspath(layer.source()) == path:
            return layer
