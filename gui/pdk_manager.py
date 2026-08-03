"""PDK 导入、激活和移除对话框。"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from database import PDKDatabase
from plugins import PluginRegistry


class PDKManagerDialog(QDialog):
    changed = Signal()

    def __init__(
        self,
        database: PDKDatabase,
        registry: PluginRegistry,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.database = database
        self.registry = registry
        self.setWindowTitle("PDK Manager")
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Imported PDKs（单选以激活）"))
        self.list_layout = QVBoxLayout()
        layout.addLayout(self.list_layout)
        self.import_button = QPushButton("Import PDK...")
        self.import_button.setIcon(
            self.style().standardIcon(self.style().StandardPixmap.SP_DialogOpenButton)
        )
        self.import_button.clicked.connect(self.import_pdk)
        layout.addWidget(self.import_button)
        self.refresh()

    def refresh(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for pdk in self.database.list_pdks():
            row = QWidget()
            row_layout = QVBoxLayout(row)
            radio = QRadioButton(f"{pdk.name}   [{pdk.plugin}]\n{pdk.path}")
            radio.setChecked(pdk.active)
            radio.toggled.connect(
                lambda checked, pdk_id=pdk.id: (
                    self.activate(pdk_id) if checked and pdk_id is not None else None
                )
            )
            self.group.addButton(radio)
            remove = QPushButton("Remove")
            remove.setIcon(
                self.style().standardIcon(self.style().StandardPixmap.SP_TrashIcon)
            )
            remove.clicked.connect(
                lambda _checked=False, pdk_id=pdk.id: (
                    self.remove(pdk_id) if pdk_id is not None else None
                )
            )
            row_layout.addWidget(radio)
            row_layout.addWidget(remove, alignment=Qt.AlignmentFlag.AlignRight)
            self.list_layout.addWidget(row)
        self.list_layout.addStretch()

    def import_pdk(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择 PDK 根目录")
        if not selected:
            return
        try:
            pdk = self.registry.import_path(Path(selected))
            self.database.import_pdk(pdk)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "无法导入", str(error))
            return
        self.refresh()
        self.changed.emit()
        QMessageBox.information(
            self,
            "导入完成",
            f"已导入 {pdk.name}，发现 {len(pdk.pcells)} 个 PCell。",
        )

    def activate(self, pdk_id: int) -> None:
        self.database.activate(pdk_id)
        self.changed.emit()

    def remove(self, pdk_id: int) -> None:
        answer = QMessageBox.question(self, "Remove PDK", "移除该 PDK 的导入记录？")
        if answer == QMessageBox.StandardButton.Yes:
            self.database.remove(pdk_id)
            self.refresh()
            self.changed.emit()
