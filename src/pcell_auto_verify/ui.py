from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QDialog, QFileDialog, QHeaderView, QLabel,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QRadioButton, QSplitter,
    QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout, QWidget,
)

from .database import PDKDatabase
from .models import PCell
from .plugins import PluginRegistry


class PDKManagerDialog(QDialog):
    changed = Signal()

    def __init__(self, database: PDKDatabase, registry: PluginRegistry, parent=None):
        super().__init__(parent)
        self.database, self.registry = database, registry
        self.setWindowTitle("PDK Manager")
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Imported PDKs（单选以激活）"))
        self.list_layout = QVBoxLayout()
        layout.addLayout(self.list_layout)
        self.import_button = QPushButton("Import PDK...")
        self.import_button.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_DialogOpenButton))
        layout.addWidget(self.import_button)
        self.import_button.clicked.connect(self.import_pdk)
        self.refresh()

    def refresh(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for pdk in self.database.list_pdks():
            row = QWidget()
            row_layout = QVBoxLayout(row)
            radio = QRadioButton(f"{pdk.name}   [{pdk.plugin}]\n{pdk.path}")
            radio.setChecked(pdk.active)
            radio.toggled.connect(lambda checked, pid=pdk.id: self.activate(pid) if checked else None)
            self.group.addButton(radio)
            remove = QPushButton("Remove")
            remove.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_TrashIcon))
            remove.clicked.connect(lambda _=False, pid=pdk.id: self.remove(pid))
            row_layout.addWidget(radio)
            row_layout.addWidget(remove, alignment=Qt.AlignmentFlag.AlignRight)
            self.list_layout.addWidget(row)
        self.list_layout.addStretch()

    def import_pdk(self):
        selected = QFileDialog.getExistingDirectory(self, "选择 PDK 根目录")
        if not selected: return
        try:
            pdk = self.registry.import_path(Path(selected))
            self.database.import_pdk(pdk)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "无法导入", str(error))
            return
        self.refresh(); self.changed.emit()
        QMessageBox.information(self, "导入完成", f"已导入 {pdk.name}，发现 {len(pdk.pcells)} 个 PCell。")

    def activate(self, pdk_id):
        self.database.activate(pdk_id); self.changed.emit()

    def remove(self, pdk_id):
        if QMessageBox.question(self, "Remove PDK", "移除该 PDK 的导入记录？") == QMessageBox.StandardButton.Yes:
            self.database.remove(pdk_id); self.refresh(); self.changed.emit()


class MainWindow(QMainWindow):
    def __init__(self, database: PDKDatabase):
        super().__init__()
        self.database = database
        self.registry = PluginRegistry()
        self.setWindowTitle("PCell Auto Verify")
        self.resize(1100, 700)
        toolbar = QToolBar("PDK")
        self.addToolBar(toolbar)
        manager = QAction(self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon), "PDK Manager", self)
        manager.triggered.connect(self.open_manager)
        toolbar.addAction(manager)
        splitter = QSplitter()
        self.cells = QListWidget()
        self.cells.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cells.currentRowChanged.connect(self.show_parameters)
        self.parameters = QTableWidget(0, 3)
        self.parameters.setHorizontalHeaderLabels(["Parameter", "Default", "Range / Choices"])
        self.parameters.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.cells); splitter.addWidget(self.parameters)
        splitter.setSizes([350, 750])
        self.setCentralWidget(splitter)
        self.current_cells: list[PCell] = []
        self.reload()

    def open_manager(self):
        dialog = PDKManagerDialog(self.database, self.registry, self)
        dialog.changed.connect(self.reload)
        dialog.exec()

    def reload(self):
        self.cells.clear(); self.parameters.setRowCount(0); self.current_cells = []
        active = next((pdk for pdk in self.database.list_pdks() if pdk.active), None)
        if active:
            self.current_cells = active.pcells
            self.cells.addItems([f"{cell.name}\n{cell.source}" for cell in active.pcells])
            self.statusBar().showMessage(f"Active PDK: {active.name} · {len(active.pcells)} PCells")
        else:
            self.statusBar().showMessage("No active PDK — open PDK Manager to import and activate one")

    def show_parameters(self, row):
        self.parameters.setRowCount(0)
        if row < 0 or row >= len(self.current_cells): return
        params = self.current_cells[row].parameters
        self.parameters.setRowCount(len(params))
        for index, param in enumerate(params):
            for column, value in enumerate((param.name, param.default, param.value_range)):
                self.parameters.setItem(index, column, QTableWidgetItem(value))

