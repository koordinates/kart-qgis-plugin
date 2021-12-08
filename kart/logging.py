from qgis.core import QgsMessageLog, Qgis

DEBUG = True
MAX_LINES = 20


def _log(msg, level=Qgis.Info):
    lines = msg.splitlines()
    if len(lines) > 20:
        msg = "\n".join(lines[:20]) + f"\n[Showing only the first {MAX_LINES} lines]"
    QgsMessageLog.logMessage(msg, "Kart", level)


def info(msg):
    _log(msg, Qgis.Info)


def error(msg):
    _log(msg, Qgis.Critical)


def debug(msg):
    if DEBUG:
        info(msg)
