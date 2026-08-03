"""应用主窗口。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core import PCell, generate_test_points
from database import PDKDatabase
from plugins import PluginRegistry

from .pdk_manager import PDKManagerDialog
from .points_dialog import TestPointsDialog


class MainWindow(QMainWindow):
    def __init__(self, database: PDKDatabase):
        super().__init__()
        self.database = database
        self.registry = PluginRegistry()
        self.current_cells: list[PCell] = []
        self.test_points: dict[int, list[dict[str, str]]] = {}
        self.setWindowTitle("PCell Auto Verify")
        self.resize(1100, 700)

        toolbar = QToolBar("PDK")
        self.addToolBar(toolbar)
        manager = QAction(
            self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon),
            "PDK Manager",
            self,
        )
        manager.triggered.connect(self.open_manager)
        toolbar.addAction(manager)

        splitter = QSplitter()
        self.cells = QListWidget()
        self.cells.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cells.currentRowChanged.connect(self.show_parameters)
        self.parameters = QTableWidget(0, 3)
        self.parameters.setHorizontalHeaderLabels(
            ["Parameter", "Default", "Range / Choices"]
        )
        self.parameters.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.parameters.itemChanged.connect(self._range_changed)
        splitter.addWidget(self.cells)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        header = QHBoxLayout()
        self.parameter_title = QLabel("Select a PCell to configure parameters")
        header.addWidget(self.parameter_title)
        header.addStretch()
        self.generate_button = QPushButton("Generate Test Points")
        self.generate_button.setEnabled(False)
        self.generate_button.clicked.connect(self.generate_points)
        header.addWidget(self.generate_button)
        self.view_button = QPushButton("View Test Points")
        self.view_button.setEnabled(False)
        self.view_button.clicked.connect(self.view_points)
        header.addWidget(self.view_button)
        right_layout.addLayout(header)
        range_help = QLabel(
            "Edit Range / Choices using min=…, max=…; choices=[…]; or low..high. "
            "Blank ranges use the default value."
        )
        range_help.setWordWrap(True)
        right_layout.addWidget(range_help)
        right_layout.addWidget(self.parameters)
        splitter.addWidget(right_panel)
        splitter.setSizes([350, 750])
        self.setCentralWidget(splitter)
        self.reload()

    def open_manager(self) -> None:
        dialog = PDKManagerDialog(self.database, self.registry, self)
        dialog.changed.connect(self.reload)
        dialog.exec()

    def reload(self) -> None:
        self.cells.clear()
        self.parameters.setRowCount(0)
        self.current_cells = []
        self.test_points.clear()
        self.generate_button.setEnabled(False)
        self.view_button.setEnabled(False)
        self.parameter_title.setText("Select a PCell to configure parameters")
        active = next(
            (pdk for pdk in self.database.list_pdks() if pdk.active), None
        )
        if active:
            self.current_cells = active.pcells
            self.cells.addItems(
                [f"{cell.name}\n{cell.source}" for cell in active.pcells]
            )
            self.statusBar().showMessage(
                f"Active PDK: {active.name} · {len(active.pcells)} PCells"
            )
        else:
            self.statusBar().showMessage(
                "No active PDK — open PDK Manager to import and activate one"
            )

    def show_parameters(self, row: int) -> None:
        self.parameters.setRowCount(0)
        self.generate_button.setEnabled(False)
        self.view_button.setEnabled(bool(self.test_points.get(row)))
        if row < 0 or row >= len(self.current_cells):
            self.parameter_title.setText("Select a PCell to configure parameters")
            return
        cell = self.current_cells[row]
        self.parameter_title.setText(f"Parameters — {cell.name}")
        parameters = cell.parameters
        self.generate_button.setEnabled(bool(parameters))
        self.parameters.blockSignals(True)
        self.parameters.setRowCount(len(parameters))
        for index, parameter in enumerate(parameters):
            values = (parameter.name, parameter.default, parameter.value_range)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column < 2:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.parameters.setItem(index, column, item)
        self.parameters.blockSignals(False)

    def _range_changed(self, item: QTableWidgetItem) -> None:
        row = self.cells.currentRow()
        if item.column() != 2 or row < 0 or row >= len(self.current_cells):
            return
        self.current_cells[row].parameters[item.row()].value_range = item.text()
        self.test_points.pop(row, None)
        self.view_button.setEnabled(False)

    def generate_points(self) -> None:
        row = self.cells.currentRow()
        if row < 0 or row >= len(self.current_cells):
            return
        points = generate_test_points(self.current_cells[row])
        self.test_points[row] = points
        self.view_button.setEnabled(bool(points))
        self.statusBar().showMessage(
            f"Generated {len(points)} test point(s) for {self.current_cells[row].name}"
        )

    def view_points(self) -> None:
        row = self.cells.currentRow()
        points = self.test_points.get(row, [])
        if row < 0 or row >= len(self.current_cells) or not points:
            return
        TestPointsDialog(self.current_cells[row], points, self).exec()
