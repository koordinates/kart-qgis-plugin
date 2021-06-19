from qgis.utils import iface

from qgis.core import QgsApplication, QgsWkbTypes, QgsProject, QgsRectangle, QgsFeature
from qgis.gui import QgsMapCanvas, QgsMapToolPan, QgsMessageBar


class HistoryDiffViewerWidget(QWidget):

    def __init__(self, dialog, server, user, repo, graph, layer=None, initialSimplify=False):
        self.graph = graph
        self.dialog = dialog
        self.server = server
        self.user = user
        self.repo = repo
        self.layer = layer
        self.afterLayer = None
        self.beforeLayer = None
        self.extraLayers = [] # layers for the "Map" tab
        QWidget.__init__(self, iface.mainWindow())
        self.setWindowFlags(Qt.Window)
        self.simplifyLog = initialSimplify
        self.initGui()
        self.tabWidget.setVisible(False)
        self.setLabelText("Select a commit to show its content")
        self.label.setVisible(False)
        if self.graph.commits:
            self.history.setCurrentItem(self.history.topLevelItem(0))
            self.itemChanged(self.history.topLevelItem(0), None)
        self.history.currentItemChanged.connect(self.itemChanged)

    def setShowPopup(self, show):
        self.history.showPopup = show

    def initGui(self):
        layout = QVBoxLayout()
        splitter = QSplitter()
        splitter.setOrientation(Qt.Vertical)

        self.history = HistoryTree(self.dialog)
        self.history.updateContent(self.server, self.user, self.repo, self.graph, self.layer)
        self.historyWithFilter = HistoryTreeWrapper(self.history)
        if self.simplifyLog:
            self.historyWithFilter.simplify(True)
        splitter.addWidget(self.historyWithFilter)
        self.tabWidget = QTabWidget()
        self.tabCanvas = QWidget()
        tabLayout = QVBoxLayout()
        tabLayout.setMargin(0)
        self.canvas = QgsMapCanvas(self.tabCanvas)
        self.canvas.setCanvasColor(Qt.white)
        self.panTool = QgsMapToolPan(self.canvas)
        self.canvas.setMapTool(self.panTool)
        tabLayout.addWidget(self.canvas)
        self.labelNoChanges = QLabel("This commit doesn't change any geometry")
        self.labelNoChanges.setAlignment(Qt.AlignCenter)
        self.labelNoChanges.setVisible(False)
        tabLayout.addWidget(self.labelNoChanges)
        self.tabCanvas.setLayout(tabLayout)
        self.summaryTextBrowser = QTextBrowser()
        self.summaryTextBrowser.setOpenLinks(False)
        self.summaryTextBrowser.anchorClicked.connect(self.summaryTextBrowserAnchorClicked)
        self.tabWidget.addTab(self.summaryTextBrowser, "Commit Summary")
        self.tabWidget.addTab(self.tabCanvas, "Map")
        tabLayout = QVBoxLayout()
        tabLayout.setMargin(0)
        self.tabDiffViewer = QWidget()
        self.diffViewer = DiffViewerWidget({})
        tabLayout.addWidget(self.diffViewer)
        self.tabDiffViewer.setLayout(tabLayout)
        self.tabWidget.addTab(self.tabDiffViewer, "Attributes")
        splitter.addWidget(self.tabWidget)
        self.label = QTextBrowser()
        self.label.setVisible(False)
        splitter.addWidget(self.label)
        self.tabWidget.setCurrentWidget(self.tabDiffViewer)

        layout.addWidget(splitter)
        self.setLayout(layout)

        exportDiffButton = QPushButton("Export this commit's DIFF for all layers")
        exportDiffButton.clicked.connect(self.exportDiffAllLayers)

        layout.addWidget(exportDiffButton)
        self.label.setMinimumHeight(self.tabWidget.height())
        self.setWindowTitle("Repository history")

    def summaryTextBrowserAnchorClicked(self,url):
        url = url.url() #convert to string
        item = self.history.currentItem()
        if item is None:
            return
        commitid = item.commit.commitid

        cmd,layerName = url.split(".",1)
        if cmd == "addLive":
            execute(lambda: self.history.exportVersion(layerName,commitid,True))
        elif cmd == "addGeoPKG":
            self.history.exportVersion(layerName,commitid,False)
        elif cmd == "exportDiff":
            execute(lambda: self.history.exportDiff(item, None,layer=layerName))

    def exportDiffAllLayers(self):
        item = self.history.currentItem()
        if item is not None:
            self.history.exportDiff(item, None)

    def setLabelText(self,text):
        self.label.setHtml("<br><br><br><center><b>{}</b></center>".format(text))

    def setContent(self, server, user, repo, graph, layer = None):
        self.server = server
        self.user = user
        self.repo = repo
        self.layer = layer
        self.graph = graph
        self.historyWithFilter.updateContent(server, user, repo, graph, layer)
        if self.history.graph.commits:
            self.history.setCurrentItem(self.history.topLevelItem(0))

    def itemChanged(self, current, previous, THRESHOLD = 1500):
        item = self.history.currentItem()
        if item is not None:
            commit = self.graph.getById(item.ref)
            if commit is None:
                self.tabWidget.setVisible(False)
                self.setLabelText("Select a commit to show its content")
                self.label.setVisible(True)
                return

            commit2 = commit.commitid + "~1"

            if not item.commit.hasParents():
                commit2 = "0000000000000000"

            total,details = self.server.diffSummary(self.user, self.repo,  commit2,commit.commitid)
            tooLargeDiff = total > THRESHOLD
            if tooLargeDiff:
                 html = "<br><br><center><b><font size=+3>Commit <font size=-0.1><tt>{}</tt></font> DIFF is too large to be shown</b></font><br>".format(commit.commitid[:8])
            else:
                html = "<br><br><center><b><font size=+3>Commit <font size=-0.1><tt>{}</tt></font> Summary</b></font><br>".format(commit.commitid[:8])
            html += "<table>"
            html += "<tr><Td style='padding:5px'><b>Layer&nbsp;Name</b></td><td style='padding:5px'><b>Additions</b></td><td style='padding:5px'><b>Deletions</b></td><td style='padding:5px'><b>Modifications</b></td><td></td><td></td><td></td></tr>"
            for detail in details.values():
                html += "<tr><td style='padding:5px'>{}</td><td style='padding:5px'><center>{:,}</center></td><td style='padding:5px'><center>{:,}</center></td><td style='padding:5px'><center>{:,}</center></td><td style='padding:5px'>{}</td><td style='padding:5px'>{}</td><td style='padding:5px'>{}</td></tr>".format(
                    detail["path"],
                    int(detail["featuresAdded"]), int(detail["featuresRemoved"]),int(detail["featuresChanged"]),
                    "<a href='addLive.{}'>Add Live</a>".format(detail["path"]),
                    "<a href='addGeoPKG.{}'>Add GeoPKG</a>".format(detail["path"]),
                    "<a href='exportDiff.{}'>Export Diff</a>".format(detail["path"])
                )
            html += "<tr></tr>"
            html += "<tr><td colspan=4>There is a total of {:,} features changed</td></tr>".format(total)
            html += "</table>"
            # html += "<br><br>There is a total of {:,} features changed".format(total)
            self.summaryTextBrowser.setHtml(html)
            self.label.setVisible(False)
            self.tabWidget.setVisible(True)
            self.tabWidget.setTabEnabled(1,not tooLargeDiff)
            self.tabWidget.setTabEnabled(2,not tooLargeDiff)
            if not tooLargeDiff:
                self.setDiffContent(commit, commit2)
        else:
            self.tabWidget.setVisible(False)
            self.setLabelText("Select a commit to show its content")
            self.label.setVisible(True)

    def setDiffContent(self, commit, commit2):
        if self.layer is None:
            layers = set(self.server.layers(self.user, self.repo, commit.commitid))
            layers2 = set(self.server.layers(self.user, self.repo, commit2))
            layers = layers.union(layers2)
        else:
            layers = [self.layer]

        diffs = {layer: execute(lambda: self.server.diff(self.user, self.repo, layer, commit.commitid, commit2)) for layer in layers}
        diffs = {key:value for (key,value) in diffs.items() if len(value) !=0}
        layers = [l for l in diffs.keys()]
        self.diffViewer.setChanges(diffs)

        self.canvas.setLayers([])
        self.removeMapLayers()
        extent = QgsRectangle()
        for layer in layers:
            if not diffs[layer]:
                continue
            beforeLayer, afterLayer = execute(lambda: self._getLayers(diffs[layer]))
            if afterLayer is not None:
                resourcesPath =  os.path.join(os.path.dirname(__file__), os.pardir, "resources")
                oldStylePath = os.path.join(resourcesPath, "{}_before.qml".format(
                                            QgsWkbTypes.geometryDisplayString(beforeLayer.geometryType())))
                newStylePath = os.path.join(resourcesPath, "{}_after.qml".format(
                                            QgsWkbTypes.geometryDisplayString(afterLayer.geometryType())))

                beforeLayer.loadNamedStyle(oldStylePath)
                afterLayer.loadNamedStyle(newStylePath)

                QgsProject.instance().addMapLayer(beforeLayer, False)
                QgsProject.instance().addMapLayer(afterLayer, False)

                extent.combineExtentWith(beforeLayer.extent())
                extent.combineExtentWith(afterLayer.extent())
                self.extraLayers.append(beforeLayer)
                self.extraLayers.append(afterLayer)
        # make extent a bit bit (10%) bigger
        # this gives some margin around the dataset (not cut-off at edges)
        if not extent.isEmpty():
            widthDelta = extent.width() * 0.05
            heightDelta = extent.height() * 0.05
            extent = QgsRectangle(extent.xMinimum() - widthDelta,
                                  extent.yMinimum() - heightDelta,
                                  extent.xMaximum() + widthDelta,
                                  extent.yMaximum() + heightDelta)

        layers = self.extraLayers
        hasChanges = False
        for layer in layers:
            if layer is not None and layer.featureCount() > 0:
                hasChanges = True
                break
        self.canvas.setLayers(layers)
        self.canvas.setExtent(extent)
        self.canvas.refresh()

        self.canvas.setVisible(hasChanges)
        self.labelNoChanges.setVisible(not hasChanges)

    def _getLayers(self, changes):
        ADDED, MODIFIED, REMOVED,  = 0, 1, 2
        def _feature(g, changeType):
            feat = QgsFeature()
            if g is not None:
                feat.setGeometry(g)
            feat.setAttributes([changeType])
            return feat
        if changes:
            f = changes[0]
            new = f["new"]
            old = f["old"]
            reference = new or old
            geomtype = QgsWkbTypes.displayString(reference.geometry().wkbType())
            oldLayer = loadLayerNoCrsDialog(geomtype + "?crs=epsg:4326&field=geogig.changeType:integer", "old", "memory")
            newLayer = loadLayerNoCrsDialog(geomtype + "?crs=epsg:4326&field=geogig.changeType:integer", "new", "memory")
            oldFeatures = []
            newFeatures = []
            for f in changes:
                new = f["new"]
                old = f["old"]
                newGeom = new.geometry() if new is not None else None
                oldGeom = old.geometry() if old is not None else None
                if oldGeom is None:
                    feature = _feature(newGeom, ADDED)
                    newFeatures.append(feature)
                elif newGeom is None:
                    feature = _feature(oldGeom, REMOVED)
                    oldFeatures.append(feature)
                elif oldGeom.asWkt() != newGeom.asWkt():
                    feature = _feature(oldGeom, MODIFIED)
                    oldFeatures.append(feature)
                    feature = _feature(newGeom, MODIFIED)
                    newFeatures.append(feature)
                else:
                    feature = _feature(newGeom, MODIFIED)
                    newFeatures.append(feature)
            oldLayer.dataProvider().addFeatures(oldFeatures)
            newLayer.dataProvider().addFeatures(newFeatures)
        else:
            oldLayer = None
            newLayer = None

        return oldLayer, newLayer

    def removeMapLayers(self):
        for layer in self.extraLayers:
            if layer is not None:
                    QgsProject.instance().removeMapLayer(layer.id())
        self.extraLayers = []

class HistoryDiffViewerDialog(QDialog):

    def __init__(self, server, user, repo, graph, layer=None):
        super(HistoryDiffViewerDialog, self).__init__()
        self.resize(1024, 768)
        layout = QVBoxLayout()
        layout.setMargin(0)
        self.bar = QgsMessageBar()
        self.bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        layout.addWidget(self.bar)
        self.history = HistoryDiffViewerWidget(repo)
        layout.addWidget(self.history)
        self.setLayout(layout)
        self.setWindowTitle("History")
        setCurrentWindow(self)

    def messageBar(self):
        return self.bar

    def closeEvent(self, evt):
        setCurrentWindow()
        self.history.removeMapLayers()
        evt.accept()
