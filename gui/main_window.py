"""应用主窗口。"""

from pathlib import PurePath

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import KLayoutVerifier, PCell, VerificationResult, generate_test_points
from database import PDKDatabase
from plugins import PluginRegistry

from .pdk_manager import PDKManagerDialog
from .points_dialog import TestPointsDialog
from .results_dialog import VerificationResultsDialog


class MainWindow(QMainWindow):
    """浏览 PCell、生成测试点并发起验证的主窗口。"""

    verification_requested = Signal(object, object)

    def __init__(self, database: PDKDatabase):
        super().__init__()
        self.database = database
        self.registry = PluginRegistry()
        self.current_cells: list[PCell] = []
        self.test_points: dict[int, list[dict[str, str]]] = {}
        self.verification_results: dict[int, list[VerificationResult]] = {}
        self.active_pdk_path = ""
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

        content_splitter = QSplitter(Qt.Orientation.Vertical)
        splitter = QSplitter()
        self.cells = QTreeWidget()
        self.cells.setHeaderLabel("PDK / PCell source path")
        self.cells.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cells.currentItemChanged.connect(self.show_parameters)
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
        self.verify_button = QPushButton("Verify")
        self.verify_button.setEnabled(False)
        self.verify_button.setToolTip(
            "Run DRC and other checks for the generated test points"
        )
        self.verify_button.clicked.connect(self.verify)
        header.addWidget(self.verify_button)
        self.results_button = QPushButton("DRC Results")
        self.results_button.setEnabled(False)
        self.results_button.setToolTip("View each result and open its generated layout")
        self.results_button.clicked.connect(self.view_results)
        header.addWidget(self.results_button)
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
        content_splitter.addWidget(splitter)

        output_panel = QWidget()
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(QLabel("Output"))
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText(
            "PCell generation and verification messages will appear here."
        )
        self.output.document().setMaximumBlockCount(2000)
        output_layout.addWidget(self.output)
        content_splitter.addWidget(output_panel)
        content_splitter.setSizes([520, 180])
        self.setCentralWidget(content_splitter)
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
        self.verification_results.clear()
        self.active_pdk_path = ""
        self.generate_button.setEnabled(False)
        self.view_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.results_button.setEnabled(False)
        self.parameter_title.setText("Select a PCell to configure parameters")
        active = next(
            (pdk for pdk in self.database.list_pdks() if pdk.active), None
        )
        if active:
            self.active_pdk_path = active.path
            self.current_cells = active.pcells
            root = QTreeWidgetItem([active.name])
            root.setData(0, Qt.ItemDataRole.UserRole, None)
            self.cells.addTopLevelItem(root)
            branches: dict[tuple[str, ...], QTreeWidgetItem] = {(): root}
            for index, cell in enumerate(active.pcells):
                parent = root
                path_parts = tuple(
                    part
                    for part in PurePath(cell.source.replace("\\", "/")).parts
                    if part not in ("/", ".")
                )
                for depth, part in enumerate(path_parts):
                    key = path_parts[: depth + 1]
                    if key not in branches:
                        branches[key] = QTreeWidgetItem(parent, [part])
                    parent = branches[key]
                cell_item = QTreeWidgetItem(parent, [cell.name])
                cell_item.setData(0, Qt.ItemDataRole.UserRole, index)
                cell_item.setToolTip(0, cell.source)
            self.cells.expandAll()
            self.statusBar().showMessage(
                f"Active PDK: {active.name} · {len(active.pcells)} PCells"
            )
            self.write_output(
                f"Loaded PDK '{active.name}' with {len(active.pcells)} PCell(s)."
            )
        else:
            self.statusBar().showMessage(
                "No active PDK — open PDK Manager to import and activate one"
            )

    def _selected_cell_index(self) -> int:
        item = self.cells.currentItem()
        if item is None:
            return -1
        index = item.data(0, Qt.ItemDataRole.UserRole)
        return index if isinstance(index, int) else -1

    def show_parameters(
        self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None
    ) -> None:
        del current, previous
        row = self._selected_cell_index()
        self.parameters.setRowCount(0)
        self.generate_button.setEnabled(False)
        self.view_button.setEnabled(bool(self.test_points.get(row)))
        self.verify_button.setEnabled(bool(self.test_points.get(row)))
        self.results_button.setEnabled(bool(self.verification_results.get(row)))
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
        row = self._selected_cell_index()
        if item.column() != 2 or row < 0 or row >= len(self.current_cells):
            return
        self.current_cells[row].parameters[item.row()].value_range = item.text()
        self.test_points.pop(row, None)
        self.verification_results.pop(row, None)
        self.view_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.results_button.setEnabled(False)

    def generate_points(self) -> None:
        row = self._selected_cell_index()
        if row < 0 or row >= len(self.current_cells):
            return
        points = generate_test_points(self.current_cells[row])
        self.test_points[row] = points
        self.verification_results.pop(row, None)
        self.view_button.setEnabled(bool(points))
        self.verify_button.setEnabled(bool(points))
        self.results_button.setEnabled(False)
        self.statusBar().showMessage(
            f"Generated {len(points)} test point(s) for {self.current_cells[row].name}"
        )
        self.write_output(
            f"Generated {len(points)} test point(s) for "
            f"'{self.current_cells[row].name}'."
        )

    def view_points(self) -> None:
        row = self._selected_cell_index()
        points = self.test_points.get(row, [])
        if row < 0 or row >= len(self.current_cells) or not points:
            return
        TestPointsDialog(self.current_cells[row], points, self).exec()

    def verify(self) -> None:
        """Generate layouts and execute the PDK's KLayout DRC deck."""
        row = self._selected_cell_index()
        points = self.test_points.get(row, [])
        if row < 0 or row >= len(self.current_cells) or not points:
            return
        cell = self.current_cells[row]
        self.verify_button.setEnabled(False)
        self.write_output(f"Running KLayout DRC for '{cell.name}' ({len(points)} point(s)) …")
        self.verification_requested.emit(cell, points)
        results = KLayoutVerifier(self.active_pdk_path).verify(cell, points)
        self.verification_results[row] = results
        passed = sum(result.passed for result in results)
        failed = len(results) - passed
        self.write_output(
            f"DRC complete for '{cell.name}': {passed} passed, {failed} failed."
        )
        for result in results:
            self.write_output(f"  #{result.index}: {'PASS' if result.passed else 'FAIL'} — {result.message}")
        self.statusBar().showMessage(f"DRC complete: {passed} passed, {failed} failed")
        self.results_button.setEnabled(bool(results))
        self.verify_button.setEnabled(True)

    def view_results(self) -> None:
        row = self._selected_cell_index()
        results = self.verification_results.get(row, [])
        if 0 <= row < len(self.current_cells) and results:
            VerificationResultsDialog(self.current_cells[row], results, self).exec()

    def write_output(self, message: str) -> None:
        """将生成或验证消息追加到主窗口输出区。"""
        self.output.appendPlainText(message)
