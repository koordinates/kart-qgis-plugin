import re

from qgis.core import QgsProviderRegistry, QgsWkbTypes
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from kart.utils import tr


def sanitizeDatasetName(name):
    """
    Returns a safe default dataset name: spaces and punctuation are
    replaced with underscores so the resulting name is a valid, easy to
    reference dataset path.
    """
    sanitized = re.sub(r"[^\w]+", "_", name, flags=re.UNICODE).strip("_")
    return sanitized or name


class MultiTableImportDialog(QDialog):
    """
    Dialog shown when the file selected for import contains more than one
    table/layer. It lets the user choose which layers to import (some or
    all of them, using checkboxes) and the name each one will have in the
    repository.

    After exec(), if accepted, `selectedTables` holds a list of
    (source_table, target_name) tuples.
    """

    def __init__(self, source, tables, existingDatasets=None, parent=None):
        super().__init__(parent)
        self.source = source
        self.tables = tables
        self.existingDatasets = set(existingDatasets or [])
        self.selectedTables = []

        self.setWindowTitle(tr("Select layers to import"))
        self.setMinimumWidth(560)
        self.setMinimumHeight(380)

        layout = QVBoxLayout()

        label = QLabel(tr("Select the layers to import into the repository:"))
        layout.addWidget(label)

        geometries = self._geometryTypes()

        self.chkSelectAll = QCheckBox(tr("Select all"))
        self.chkSelectAll.setTristate(False)
        self.chkSelectAll.stateChanged.connect(self._selectAllChanged)
        selectAllLayout = QHBoxLayout()
        selectAllLayout.addWidget(self.chkSelectAll)
        selectAllLayout.addStretch()
        layout.addLayout(selectAllLayout)

        self.table = QTableWidget(len(tables), 3)
        self.table.setHorizontalHeaderLabels(
            [tr("Layer"), tr("Geometry"), tr("Name in repository")]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        for row, tableName in enumerate(tables):
            itemName = QTableWidgetItem(tableName)
            itemName.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            itemName.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, itemName)

            itemGeom = QTableWidgetItem(geometries.get(tableName, ""))
            itemGeom.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, 1, itemGeom)

            itemTarget = QTableWidgetItem(sanitizeDatasetName(tableName))
            self.table.setItem(row, 2, itemTarget)

        self.table.itemChanged.connect(self._itemChanged)
        layout.addWidget(self.table)

        self.chkSelectAll.setCheckState(Qt.CheckState.Checked)

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttonBox.accepted.connect(self.okClicked)
        buttonBox.rejected.connect(self.reject)
        layout.addWidget(buttonBox)

        self.setLayout(layout)

    def _geometryTypes(self):
        """
        Best-effort enrichment: ask QGIS for the sublayers of the source to
        display the geometry type of each table. Failures are silently
        ignored (the column is simply left empty), since this information
        is cosmetic and the authoritative table list comes from Kart.
        """
        geometries = {}
        try:
            sublayers = QgsProviderRegistry.instance().querySublayers(self.source)
            for sublayer in sublayers:
                try:
                    geometries[sublayer.name()] = QgsWkbTypes.displayString(
                        sublayer.wkbType()
                    )
                except Exception:
                    pass
        except Exception:
            pass
        return geometries

    def _selectAllChanged(self, state):
        self.table.blockSignals(True)
        checkState = (
            Qt.CheckState.Checked
            if state == Qt.CheckState.Checked.value
            else Qt.CheckState.Unchecked
        )
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(checkState)
        self.table.blockSignals(False)

    def _itemChanged(self, item):
        if item.column() == 0:
            self.chkSelectAll.blockSignals(True)
            states = [
                self.table.item(row, 0).checkState() == Qt.CheckState.Checked
                for row in range(self.table.rowCount())
            ]
            if all(states):
                self.chkSelectAll.setCheckState(Qt.CheckState.Checked)
            elif not any(states):
                self.chkSelectAll.setCheckState(Qt.CheckState.Unchecked)
            else:
                self.chkSelectAll.setTristate(True)
                self.chkSelectAll.setCheckState(Qt.CheckState.PartiallyChecked)
            self.chkSelectAll.blockSignals(False)

    def okClicked(self):
        selected = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked:
                sourceName = self.table.item(row, 0).text()
                targetName = self.table.item(row, 2).text().strip()
                selected.append((sourceName, targetName or sourceName))

        if not selected:
            QMessageBox.warning(self, tr("Import"), tr("No layers are selected"))
            return

        targetNames = [target for _, target in selected]
        duplicated = {name for name in targetNames if targetNames.count(name) > 1}
        if duplicated:
            QMessageBox.warning(
                self,
                tr("Import"),
                tr("Duplicated dataset name: {name}").format(
                    name=", ".join(sorted(duplicated))
                ),
            )
            return

        conflicting = sorted(set(targetNames) & self.existingDatasets)
        if conflicting:
            QMessageBox.warning(
                self,
                tr("Import"),
                tr("A dataset named '{name}' already exists in the repository").format(
                    name=", ".join(conflicting)
                ),
            )
            return

        self.selectedTables = selected
        self.accept()
