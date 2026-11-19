"""应用主窗口。"""

from dataclasses import replace
from pathlib import Path, PurePath
from subprocess import TimeoutExpired

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
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

from core import (
    KLayoutVerifier,
    PCell,
    VerificationResult,
    inferred_range,
)
from core.domestic180_verification import run_extraction as run_domestic180_extraction
from core.models import GeneratedLayout
from core.nmos_extraction import ExtractionResult, run_mos_extraction
from core.sky130_inverter import INVERTER_NAME, SKY130_REGRESSION_CELLS, inverter_pcell
from core.sky130_library import is_sky130a
from core.sky130_nmos import MOS_PCELL_NAMES
from core.test_points import default_test_point
from database import PDKDatabase
from plugins import PluginRegistry

from .pdk_manager import PDKManagerDialog
from .points_dialog import TestPointsDialog
from .results_dialog import ExtractionResultsDialog, VerificationResultsDialog


class MainWindow(QMainWindow):
    """浏览 PCell、生成测试点并发起验证的主窗口。"""

    verification_requested = Signal(object, object)

    def __init__(self, database: PDKDatabase):
        super().__init__()
        self.database = database
        self.registry = PluginRegistry()
        self.current_cells: list[PCell] = []
        self.test_points: dict[int, list[GeneratedLayout]] = {}
        self.verification_results: dict[int, list[VerificationResult]] = {}
        self.extraction_results: dict[tuple[int, str], list[ExtractionResult]] = {}
        self.callback_editable: dict[int, dict[str, bool]] = {}
        self.active_pdk_path = ""
        self.active_sky130a = False
        self.active_domestic180 = False
        self.setWindowTitle("PCell Auto Verify")
        self.resize(1100, 700)

        self.setStyleSheet(
            "QToolBar { spacing: 6px; padding: 5px; }"
            "QPushButton { min-height: 26px; padding: 2px 10px; }"
            "QHeaderView::section { font-weight: 600; padding: 6px; }"
        )
        toolbar = QToolBar("Verification tools")
        toolbar.setObjectName("verificationToolbar")
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        self.manager_action = QAction(
            self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon),
            "PDK Manager",
            self,
        )
        self.manager_action.triggered.connect(self.open_manager)
        self.reload_action = QAction(
            self.style().standardIcon(self.style().StandardPixmap.SP_BrowserReload),
            "Reload",
            self,
        )
        self.reload_action.triggered.connect(self.reload)
        self.generate_action = QAction(
            self.style().standardIcon(
                self.style().StandardPixmap.SP_FileDialogNewFolder
            ),
            "Automatic Test Points Generation",
            self,
        )
        self.generate_action.triggered.connect(self.generate_points)
        self.manual_generate_action = QAction(
            self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon),
            "Manual Test Points Generation",
            self,
        )
        self.manual_generate_action.triggered.connect(self.generate_manual_point)
        self.view_points_action = QAction(
            self.style().standardIcon(
                self.style().StandardPixmap.SP_FileDialogContentsView
            ),
            "View Points",
            self,
        )
        self.view_points_action.triggered.connect(self.view_points)
        self.verify_action = QAction(
            self.style().standardIcon(self.style().StandardPixmap.SP_DialogApplyButton),
            "DRC",
            self,
        )
        self.verify_action.triggered.connect(self.verify)
        self.results_action = QAction(
            self.style().standardIcon(
                self.style().StandardPixmap.SP_FileDialogDetailedView
            ),
            "Verification Results",
            self,
        )
        self.results_action.triggered.connect(self.view_results)
        for action in (self.manager_action, self.reload_action):
            toolbar.addAction(action)
        toolbar.addSeparator()
        verification_actions = (
            self.generate_action,
            self.manual_generate_action,
            self.view_points_action,
            self.verify_action,
            self.results_action,
        )
        for action in verification_actions:
            toolbar.addAction(action)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.manager_action)
        file_menu.addAction(self.reload_action)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close)
        verify_menu = self.menuBar().addMenu("&Verification")
        for action in verification_actions:
            verify_menu.addAction(action)
        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(toolbar.toggleViewAction())
        help_menu = self.menuBar().addMenu("&Help")
        about_action = help_menu.addAction("About PCell Auto Verify")
        about_action.triggered.connect(
            lambda: self.statusBar().showMessage(
                "PCell Auto Verify · automated PCell boundary verification", 5000
            )
        )

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
        right_layout.addWidget(self.parameter_title)
        self.generate_button = QPushButton("Automatic Test Points Generation")
        self.generate_button.setEnabled(False)
        self.generate_button.clicked.connect(self.generate_points)
        header.addWidget(self.generate_button)
        self.manual_generate_button = QPushButton("Manual Test Points Generation")
        self.manual_generate_button.setEnabled(False)
        self.manual_generate_button.clicked.connect(self.generate_manual_point)
        header.addWidget(self.manual_generate_button)
        self.view_button = QPushButton("View Test Points")
        self.view_button.setEnabled(False)
        self.view_button.clicked.connect(self.view_points)
        header.addWidget(self.view_button)
        header.addStretch()
        right_layout.addLayout(header)
        checks = QHBoxLayout()
        self.verify_button = QPushButton("DRC")
        self.verify_button.setEnabled(False)
        self.verify_button.setToolTip(
            "Run DRC on the generated GDS files"
        )
        self.verify_button.clicked.connect(self.verify)
        checks.addWidget(self.verify_button)
        self.results_button = QPushButton("DRC Results")
        self.results_button.setEnabled(False)
        self.results_button.setToolTip("View DRC results and the PDF summary")
        self.results_button.clicked.connect(self.view_results)
        checks.addWidget(self.results_button)
        self.extraction_buttons = {}
        for mode in ("lvs", "rcx"):
            run_button = QPushButton(mode.upper())
            run_button.setObjectName(f"{mode}Button")
            run_button.setToolTip("Run on generated GDS from a supported PDK")
            run_button.clicked.connect(lambda checked=False, mode=mode: self.run_extraction(mode))
            results_button = QPushButton(f"{mode.upper()} Results")
            results_button.setObjectName(f"{mode}ResultsButton")
            results_button.clicked.connect(lambda checked=False, mode=mode: self.view_extraction(mode))
            checks.addWidget(run_button)
            checks.addWidget(results_button)
            self.extraction_buttons[mode] = run_button, results_button
        checks.addStretch()
        right_layout.addLayout(checks)
        range_help = QLabel(
            "Defaults and Range / Choices are editable. Use min=…, max=…; "
            "choices=[…]; or low..high. A blank, unresolved default is omitted "
            "so the PCell can use its native runtime default."
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

    def _sync_actions(self) -> None:
        self.generate_action.setEnabled(self.generate_button.isEnabled())
        self.manual_generate_action.setEnabled(self.manual_generate_button.isEnabled())
        self.view_points_action.setEnabled(self.view_button.isEnabled())
        self.verify_action.setEnabled(self.verify_button.isEnabled())
        self.results_action.setEnabled(self.results_button.isEnabled())
        row = self._selected_cell_index()
        can_extract = (
            0 <= row < len(self.current_cells)
            and (self.active_domestic180 or (
                self.active_sky130a and self.current_cells[row].name in (*MOS_PCELL_NAMES, INVERTER_NAME)
            ))
            and any(point.layout_path for point in self.test_points.get(row, []))
        )
        for mode, (run_button, results_button) in self.extraction_buttons.items():
            run_button.setEnabled(can_extract)
            results_button.setEnabled((row, mode) in self.extraction_results)

    def open_manager(self) -> None:
        dialog = PDKManagerDialog(self.database, self.registry, self)
        dialog.changed.connect(self.reload)
        dialog.exec()

    def reload(self) -> None:
        self.cells.clear()
        self.parameters.setRowCount(0)
        self.current_cells = []
        self.test_points.clear()
        self.callback_editable.clear()
        self.verification_results.clear()
        self.extraction_results.clear()
        self.active_pdk_path = ""
        self.active_sky130a = False
        self.active_domestic180 = False
        self.generate_button.setEnabled(False)
        self.manual_generate_button.setEnabled(False)
        self.view_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.results_button.setEnabled(False)
        self._sync_actions()
        self.parameter_title.setText("Select a PCell to configure parameters")
        active = next(
            (pdk for pdk in self.database.list_pdks() if pdk.active), None
        )
        flat = active is not None and active.plugin == "open-pdks" and is_sky130a(active.name)
        header = self.cells.header()
        header.setStretchLastSection(not flat)
        header.setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents if flat else QHeaderView.ResizeMode.Interactive
        )
        if active:
            self.active_pdk_path = active.path
            self.active_sky130a = is_sky130a(active.name)
            self.active_domestic180 = active.plugin == "domestic180"
            self.current_cells = list(active.pcells)
            if flat and set(MOS_PCELL_NAMES).issubset(cell.name for cell in active.pcells):
                self.current_cells.append(inverter_pcell())
            root = QTreeWidgetItem([active.name])
            root.setData(0, Qt.ItemDataRole.UserRole, None)
            self.cells.addTopLevelItem(root)
            branches: dict[tuple[str, ...], QTreeWidgetItem] = {(): root}
            for index, cell in enumerate(self.current_cells):
                parent = root
                path_parts = () if flat else tuple(
                    part
                    for part in PurePath(cell.source.replace("\\", "/")).parts
                    if part not in ("/", ".")
                )
                if flat and cell.name == INVERTER_NAME:
                    path_parts = ("Custom PCells",)
                for depth, part in enumerate(path_parts):
                    key = path_parts[: depth + 1]
                    if key not in branches:
                        branches[key] = QTreeWidgetItem(parent, [part])
                    parent = branches[key]
                label = cell.name
                tooltip = cell.source
                if flat and cell.source and Path(cell.source).suffix == ".py":
                    source = Path(cell.source)
                    label = f"{cell.name} ({source.name})"
                    tooltip = str(Path(active.path) / source)
                cell_item = QTreeWidgetItem(parent, [label])
                cell_item.setData(0, Qt.ItemDataRole.UserRole, index)
                cell_item.setToolTip(0, tooltip)
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
        self.manual_generate_button.setEnabled(False)
        self.view_button.setEnabled(bool(self.test_points.get(row)))
        self.verify_button.setEnabled(any(point.layout_path for point in self.test_points.get(row, [])))
        self.results_button.setEnabled(bool(self.verification_results.get(row)))
        if row < 0 or row >= len(self.current_cells):
            self.parameter_title.setText("Select a PCell to configure parameters")
            self._sync_actions()
            return
        cell = self.current_cells[row]
        self.parameter_title.setText(f"Parameters — {cell.name}")
        parameters = cell.parameters
        self.generate_button.setEnabled(True)
        self.manual_generate_button.setEnabled(True)
        self.parameters.blockSignals(True)
        self.parameters.setRowCount(len(parameters))
        for index, parameter in enumerate(parameters):
            if not cell.library_path and not parameter.value_range.strip():
                parameter.value_range = inferred_range(parameter)
            values = (parameter.name, parameter.default, parameter.value_range)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(parameter.description)
                if (column == 0 or parameter.hidden or parameter.readonly
                        or not self.callback_editable.get(row, {}).get(parameter.name, True)):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.parameters.setItem(index, column, item)
        self.parameters.blockSignals(False)
        self._sync_actions()

    def _range_changed(self, item: QTableWidgetItem) -> None:
        row = self._selected_cell_index()
        if item.column() not in (1, 2) or row < 0 or row >= len(self.current_cells):
            return
        parameter = self.current_cells[row].parameters[item.row()]
        if parameter.hidden or parameter.readonly:
            return
        if not self.callback_editable.get(row, {}).get(parameter.name, True):
            return
        if item.column() == 2:
            parameter.value_range = item.text()
            return

        cell = self.current_cells[row]
        proposed = default_test_point(cell)
        if item.text().strip():
            proposed[parameter.name] = item.text()
        else:
            proposed.pop(parameter.name, None)
        try:
            result = KLayoutVerifier.evaluate_parameter_edit(
                self.active_pdk_path, cell, parameter.name, proposed,
            )
        except (OSError, ValueError, TimeoutExpired) as error:
            self.show_parameters(None, None)
            QMessageBox.warning(self, "PCell Callback", str(error))
            return

        parameter.default = proposed.get(parameter.name, "")
        if result is None:
            return
        self.callback_editable[row] = result["editable"]
        messages = list(result["messages"])
        for field in cell.parameters:
            if field.name in result["values"]:
                effective = result["values"][field.name]
                previous = field.default
                if KLayoutVerifier._values({"value": previous}) != KLayoutVerifier._values({"value": effective}):
                    messages.append(f"{field.name}: {previous or '(unset)'} → {effective or '(unset)'}")
                field.default = effective
        self.show_parameters(None, None)
        if messages:
            QMessageBox.information(self, "PCell Callback", "\n".join(dict.fromkeys(messages)))

    def generate_points(self) -> None:
        row = self._selected_cell_index()
        if row < 0 or row >= len(self.current_cells):
            return
        cell = self.current_cells[row]
        defaults = default_test_point(cell)
        points = [defaults]
        if self.active_sky130a and cell.name in SKY130_REGRESSION_CELLS:
            points.append({**defaults, "metal1_test_width": "0.035"})
        elif self.active_domestic180:
            points.append({**defaults, "metal_width": "0.12"})
        self._generate_layouts(row, points, "automatic")

    def generate_manual_point(self) -> None:
        row = self._selected_cell_index()
        if 0 <= row < len(self.current_cells):
            self._generate_layouts(row, [default_test_point(self.current_cells[row])], "manual")

    def _generate_layouts(self, row: int, points: list[dict[str, str]], origin: str) -> None:
        cell = self.current_cells[row]
        self.verification_results.pop(row, None)
        for mode in self.extraction_buttons:
            self.extraction_results.pop((row, mode), None)
        try:
            layouts = KLayoutVerifier(self.active_pdk_path).generate_layouts(cell, points)
        except OSError as error:
            layouts = [
                GeneratedLayout(index, point, f"GDS generation failed: {error}")
                for index, point in enumerate(points, 1)
            ]
        previous = self.test_points.get(row, [])
        created = [replace(point, origin=origin) for point in layouts]
        if origin == "manual":
            combined = [*previous, *created]
        else:
            combined = [*created, *(point for point in previous if point.origin == "manual")]
        self.test_points[row] = [
            replace(point, index=index) for index, point in enumerate(combined, 1)
        ]
        self.view_button.setEnabled(bool(combined))
        self.verify_button.setEnabled(any(point.layout_path for point in combined))
        self.results_button.setEnabled(False)
        self._sync_actions()
        first_new = len(previous) if origin == "manual" else 0
        for point in self.test_points[row][first_new:first_new + len(layouts)]:
            message = f"GDS: {point.layout_path}" if point.layout_path else point.message
            self.write_output(f"  #{point.index}: {message}")
        self.statusBar().showMessage(
            f"Generated {sum(bool(point.layout_path) for point in layouts)}/{len(layouts)} GDS layout(s)"
        )

    def view_points(self) -> None:
        row = self._selected_cell_index()
        points = self.test_points.get(row, [])
        if row < 0 or row >= len(self.current_cells) or not points:
            return
        TestPointsDialog(self.current_cells[row], points, self).exec()

    def verify(self) -> None:
        """Run DRC against the layouts already generated for this PCell."""
        row = self._selected_cell_index()
        points = self.test_points.get(row, [])
        if row < 0 or row >= len(self.current_cells):
            return
        first_layout = next((point.layout_path for point in points if point.layout_path), None)
        if first_layout is None:
            return
        cell = self.current_cells[row]
        self.verify_button.setEnabled(False)
        self._sync_actions()
        self.write_output(
            f"Running DRC for '{cell.name}' ({len(points)} point(s)) …"
        )
        self.verification_requested.emit(cell, [point.parameters for point in points])
        try:
            results = KLayoutVerifier(
                self.active_pdk_path, str(Path(first_layout).parent)
            ).check_layouts(points)
        except OSError as error:
            results = [
                VerificationResult(
                    point.index, point.parameters, False, f"Unable to access verification files: {error}"
                )
                for point in points
            ]
        self.verification_results[row] = results
        passed = sum(result.passed for result in results)
        failed = len(results) - passed
        self.write_output(
            f"DRC complete for '{cell.name}': {passed} passed, {failed} failed."
        )
        for result in results:
            self.write_output(
                f"  #{result.index}: "
                f"{'PASS' if result.passed else 'FAIL'} — {result.message}"
            )
        self.statusBar().showMessage(f"DRC complete: {passed} passed, {failed} failed")
        self.results_button.setEnabled(bool(results))
        self.verify_button.setEnabled(True)
        self._sync_actions()

    def view_results(self) -> None:
        row = self._selected_cell_index()
        results = self.verification_results.get(row, [])
        if 0 <= row < len(self.current_cells) and results:
            VerificationResultsDialog(self.current_cells[row], results, self).exec()

    def run_extraction(self, mode: str) -> None:
        row = self._selected_cell_index()
        run_button, _ = self.extraction_buttons[mode]
        if not run_button.isEnabled():
            return
        run_button.setEnabled(False)
        label = mode.upper()
        self.write_output(f"Running {label} for '{self.current_cells[row].name}' …")
        extractor = run_domestic180_extraction if self.active_domestic180 else run_mos_extraction
        results = [
            extractor(Path(self.active_pdk_path).resolve(), point, mode)
            for point in self.test_points[row]
        ]
        self.extraction_results[row, mode] = results
        for result in results:
            self.write_output(f"  #{result.index}: {label} {result.status}")
        self._sync_actions()

    def view_extraction(self, mode: str) -> None:
        row = self._selected_cell_index()
        results = self.extraction_results.get((row, mode))
        if results:
            ExtractionResultsDialog(mode.upper(), results, self).exec()

    def write_output(self, message: str) -> None:
        """将生成或验证消息追加到主窗口输出区。"""
        self.output.appendPlainText(message)
