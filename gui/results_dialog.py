"""Detailed DRC results with links to generated layouts."""

from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core import PCell, VerificationResult


class VerificationResultsDialog(QDialog):
    def __init__(self, pcell: PCell, results: list[VerificationResult], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"DRC Results — {pcell.name}")
        self.resize(980, 560)
        layout = QVBoxLayout(self)
        table = QTableWidget(len(results), 4)
        table.setHorizontalHeaderLabels(["#", "Result", "Parameters / Message", "Layout"])
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, result in enumerate(results):
            table.setItem(row, 0, QTableWidgetItem(str(result.index)))
            status = QTableWidgetItem("PASS" if result.passed else "FAIL")
            status.setForeground(QColor("#16803c" if result.passed else "#c62828"))
            table.setItem(row, 1, status)
            details = ", ".join(f"{key}={value}" for key, value in result.parameters.items())
            table.setItem(row, 2, QTableWidgetItem(f"{details}\n{result.message}"))
            if result.layout_path:
                button = QPushButton("Open Layout")
                button.clicked.connect(lambda checked=False, path=result.layout_path: self._open(path))
                table.setCellWidget(row, 3, button)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _open(self, path: str) -> None:
        if not Path(path).exists() or not QProcess.startDetached("klayout", [path]):
            QMessageBox.warning(self, "Open Layout", f"Unable to open layout:\n{path}")
