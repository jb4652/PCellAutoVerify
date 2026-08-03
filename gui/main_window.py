"""应用主窗口。"""

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QListWidget,
    QMainWindow,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
)

from core import PCell
from database import PDKDatabase
from plugins import PluginRegistry

from .pdk_manager import PDKManagerDialog


class MainWindow(QMainWindow):
    def __init__(self, database: PDKDatabase):
        super().__init__()
        self.database = database
        self.registry = PluginRegistry()
        self.current_cells: list[PCell] = []
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
        splitter.addWidget(self.cells)
        splitter.addWidget(self.parameters)
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
        if row < 0 or row >= len(self.current_cells):
            return
        parameters = self.current_cells[row].parameters
        self.parameters.setRowCount(len(parameters))
        for index, parameter in enumerate(parameters):
            values = (parameter.name, parameter.default, parameter.value_range)
            for column, value in enumerate(values):
                self.parameters.setItem(index, column, QTableWidgetItem(value))
