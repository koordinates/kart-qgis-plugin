import math

import os
from functools import partial

from qgis.core import QgsApplication, Qgis
from qgis.utils import iface
from qgis.gui import QgsMessageBar

from qgis.PyQt.QtCore import Qt, pyqtSignal, QPoint, QRectF, QPointF, QLineF
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QColor, QPainterPath, QPen, QPolygonF
from qgis.PyQt.QtWidgets import (QTreeWidget, QAbstractItemView, QAction, QMenu,
                                 QTreeWidgetItem, QWidget, QVBoxLayout, QDialog,
                                 QSizePolicy, QLabel, QInputDialog)

COMMIT_GRAPH_HEIGHT = 20
RADIUS = 5
PEN_WIDTH = 4

COLORS = [QColor(Qt.red),
          QColor(Qt.green),
          QColor(Qt.blue),
          QColor(Qt.black),
          QColor(255,166,0),
          QColor(Qt.darkGreen),
          QColor(Qt.darkBlue),
          QColor(Qt.cyan),
          QColor(Qt.magenta)]

def icon(f):
    return QIcon(os.path.join(os.path.dirname(__file__),
                              "img", f))

resetIcon = icon("reset.png")
diffIcon = icon("diff-selected.png")
deleteIcon = QgsApplication.getThemeIcon('/mActionDeleteSelected.svg')
infoIcon = icon("repo-summary.png")
tagIcon = icon("tag.gif")
mergeIcon = icon("merge-24.png")

class HistoryTree(QTreeWidget):

    historyChanged = pyqtSignal()

    def __init__(self, repo, parent):
        super(HistoryTree, self).__init__()
        self.repo = repo
        self.parent = parent
        self.initGui()

    def scrollTo(self, index, hint):
        oldH = self.horizontalScrollBar().value()
        super().scrollTo(index, hint)
        self.horizontalScrollBar().setValue(oldH)

    def initGui(self):
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.header().setStretchLastSection(True)
        #self.setAlternatingRowColors(True)
        self.setHeaderLabels(["Graph", "Description", "Author", "Date", "CommitID"])
        self.customContextMenuRequested.connect(self._showPopupMenu)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.populate()

    def _showPopupMenu(self, point):
        point = self.mapToGlobal(point)
        selected = self.selectedItems()
        if selected and len(selected) == 1:
            actions = {"Show changes for this commit": self.showChanges,
                       "Reset current branch to this commit": self.resetBranch,
                       "Create branch at this commit": self.createBranch}
            item = self.currentItem()
            for ref in item.commit['refs']:
                actions[f"Switch to branch '{ref}'"]: partial(self.switchBranch, ref)
            menu = QMenu()
            for text, func in actions.items():
                action = QAction(text, menu)
                action.triggered.connect(partial(func, item))
                menu.addAction(action)
            menu.exec_(point)
        elif selected and len(selected) == 2:
            itema = selected[0]
            itemb = selected[1]
            menu = QMenu()
            for text, func in actions.items():
                action = QAction(text, menu)
                action.triggered.connect(partial(func, itema, itemb))
                menu.addAction(action)
            menu.exec_(point)

    def switchBranch(self, branch, item):
        self.repo.checkout(branch)
        self.populate()

    def createBranch(self, item):
        name, ok = QInputDialog.getText(self, "Create branch", "Enter name of branch to create")
        if ok and name:
            self.repo.createBranch(name, item.commit['commit'])
            self.message("Branch correctly created", Qgis.Success)
            self.populate()

    def showChanges(self, item):
        dialog = DiffDialog(self, item)
        dialog.exec()

    def resetBranch(self, item):
        self.repo.reset(item.commit['commit'])
        self.message("Branch correctly reset to selected commit", Qgis.Success)
        self.populate()

    def message(self, text, level):
        self.parent.bar.pushMessage(text, level, duration = 5)

    def drawLine(self, painter, commit, parent):
        commitRow = self.commitRows[commit.commitid]
        commitCol = self.commitColumns[commit.commitid]
        parentRow = self.commitRows[parent.commitid]
        parentCol = self.commitColumns[parent.commitid]
        commitX = self.RADIUS * 3 + commitCol * self.COLUMN_SEPARATION
        parentX = self.RADIUS * 3 + parentCol * self.COLUMN_SEPARATION
        commitY = commitRow * self.COMMIT_GRAPH_HEIGHT
        parentY = parentRow * self.COMMIT_GRAPH_HEIGHT
        color = self._columnColor(parentCol)

        if parent is not None and self.graph.isFauxLink(parent.commitid, commit.commitid)\
                and len(parent.childrenIds)>1:
            # draw a faux line
            path = QPainterPath()
            path.moveTo(parentX, parentY)
            path.lineTo(commitX , commitY)

            color = QColor(255,160,255)
            pen = QPen()
            pen.setWidth(2)
            pen.setBrush(color)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.drawPath(path)

            # draw arrow
            # draw arrow
            ARROW_POINT_SIZE = 9
            painter.setPen(color)
            painter.setBrush(color)
            line = QLineF(commitX , commitY, parentX, parentY)

            angle = math.acos(line.dx() / line.length())
            if line.dy() >= 0:
                angle = 2.0 * math.pi - angle

            sourcePoint = QPointF(commitX,commitY)
            sourceArrowP1 = sourcePoint + QPointF(math.sin(angle + math.pi / 3) * ARROW_POINT_SIZE,
                                                       math.cos(angle + math.pi / 3) * ARROW_POINT_SIZE)
            sourceArrowP2 = sourcePoint + QPointF(math.sin(angle + math.pi - math.pi / 3) * ARROW_POINT_SIZE,
                                                       math.cos(angle + math.pi - math.pi / 3) * ARROW_POINT_SIZE)
            arrow = QPolygonF([line.p1(), sourceArrowP1, sourceArrowP2])
            painter.drawPolygon(arrow)
            return

        path = QPainterPath()
        painter.setBrush(color)
        painter.setPen(color)

        if parentCol != commitCol:
            if parent.isFork() and commit.getParents()[0].commitid == parent.commitid:
                path.moveTo(commitX, commitY)
                path.lineTo(commitX, parentY)
                if parentX<commitX:
                    path.lineTo(parentX + self.RADIUS + 1, parentY)
                else:
                    path.lineTo(parentX - self.RADIUS, parentY)
                color = self._columnColor(commitCol)
            else:
                path2 = QPainterPath()
                path2.moveTo(commitX + self.RADIUS + 1, commitY)
                path2.lineTo(commitX + self.RADIUS + self.COLUMN_SEPARATION / 2, commitY + self.COLUMN_SEPARATION / 3)
                path2.lineTo(commitX + self.RADIUS + self.COLUMN_SEPARATION / 2, commitY - self.COLUMN_SEPARATION / 3)
                path2.lineTo(commitX + + self.RADIUS + 1, commitY)
                painter.setBrush(color)
                painter.setPen(color)
                painter.drawPath(path2)
                path.moveTo(commitX + self.RADIUS + self.COLUMN_SEPARATION / 2, commitY)
                path.lineTo(parentX, commitY)
                path.lineTo(parentX, parentY)

            if parent.isFork():
                if commitCol in self.columnColor.keys():
                    del self.columnColor[commitCol]

        else:
            path.moveTo(commitX, commitY)
            path.lineTo(parentX, parentY)

        pen = QPen(color, self.PEN_WIDTH, Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin)
        painter.strokePath(path, pen)

        if not commit.commitid in self.linked:
            y = commitRow * self.COLUMN_SEPARATION
            x = self.RADIUS * 3 + commitCol * self.COLUMN_SEPARATION
            painter.setPen(color)
            painter.setBrush(color)
            painter.drawEllipse(QPoint(x, y), self.RADIUS, self.RADIUS)
            self.linked.append(commit.commitid)

    def _columnColor(self, column):
        if column in self.columnColor:
            color = self.columnColor[column]
        elif column == 0:
            self.lastColor += 1
            color = self.COLORS[0]
            self.columnColor[column] = color
        else:
            self.lastColor += 1
            color = self.COLORS[(self.lastColor % (len(self.COLORS)-1)) + 1]
            self.columnColor[column] = color
        return color

    def populate(self):
        self.log = {c['commit']: c for c in self.repo.log()}

        self.clear()

        maxcol = max([c['commitColumn'] for c in self.log.values()])
        width = RADIUS * maxcol * 2 + 3 * RADIUS

        for i, commit in enumerate(self.log.values()):
            item = CommitTreeItem(commit, self)
            self.addTopLevelItem(item)
            img = self.graphImage(commit, width)
            w = GraphWidget(img)
            w.setFixedHeight(COMMIT_GRAPH_HEIGHT)
            self.setItemWidget(item, 0, w)
            self.setColumnWidth(0, width)

        for i in range(1, 4):
            self.resizeColumnToContents(i)

        self.expandAll()

        self.header().resizeSection(0, width)

    def graphImage(self, commit, width):
        image = QPixmap(width, COMMIT_GRAPH_HEIGHT).toImage()
        qp = QPainter(image)
        qp.fillRect(QRectF(0, 0, width, COMMIT_GRAPH_HEIGHT), Qt.white);
        col = commit['commitColumn']
        y = COMMIT_GRAPH_HEIGHT / 2
        x = RADIUS + RADIUS * 2 * col
        color = COLORS[col]
        qp.setPen(color)
        qp.setBrush(color)
        qp.drawEllipse(QPoint(x, y), RADIUS, RADIUS)
        qp.end()
        return image

class GraphWidget(QWidget):

    def __init__(self, img):
        QWidget.__init__(self)
        self.setFixedWidth(img.width())
        self.img = img

    def paintEvent(self, e):
        painter = QPainter(self)
        #painter.begin(self);
        painter.drawImage(0, 0, self.img)
        painter.end()

class CommitTreeItem(QTreeWidgetItem):

    def __init__(self, commit, parent):
        QTreeWidgetItem.__init__(self, parent)
        self.commit = commit
        if commit["refs"]:
            labelslist = []
            for label in commit["refs"]:
                if "HEAD" in label:
                    labelslist.append('<span style="background-color:crimson; color:white"> '
                                      f'&nbsp;&nbsp;{label.split("->")[0].strip()}&nbsp;&nbsp;</span>')
                else:
                    labelslist.append('<span style="background-color:salmon; color:white"> '
                                      f'&nbsp;&nbsp;{label}&nbsp;&nbsp;</span>')
            labels = " ".join(labelslist) + "&nbsp;&nbsp;"
        else:
            labels = ""
        text = f"{labels}<b>{commit['message'].splitlines()[0]}</b>"
        qlabel = QLabel(text)
        qlabel.setStyleSheet("QLabel {padding-left: 15px;}");
        parent.setItemWidget(self, 1, qlabel)
        self.setText(1, "")
        self.setText(2, commit['authorName'])
        self.setText(3, commit['authorTime'])
        self.setText(4, commit['commit'])


class HistoryDialog(QDialog):

    def __init__(self, repo):
        super(HistoryDialog, self).__init__(iface.mainWindow())
        self.setWindowFlags(Qt.Window)
        layout = QVBoxLayout()
        layout.setMargin(0)
        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        layout.addWidget(self.bar)
        self.history = HistoryTree(repo, self)
        layout.addWidget(self.history)
        self.setLayout(layout)
        self.setWindowTitle("History")
        self.resize(1024, 768)

