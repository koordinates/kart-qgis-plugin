from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsProcessingAlgorithm


class KartAlgorithm(QgsProcessingAlgorithm):
    def createInstance(self):
        return type(self)()

    def name(self):
        return f"kart_{self.__class__.__name__.lower()}"

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def initAlgorithm(self, config=None):
        return {}
