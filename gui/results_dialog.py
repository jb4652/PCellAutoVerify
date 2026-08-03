"""Detailed DRC results with links to generated layouts."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QLabel, QMessageBox, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core import PCell, VerificationResult


class VerificationResultsDialog(QDialog):
    def __init__(self, pcell: PCell, results: list[VerificationResult], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"DRC Results — {pcell.name}")
        self.resize(980, 560)
        layout = QVBoxLayout(self)
        table = QTableWidget(len(results), 5)
        table.setHorizontalHeaderLabels(
            ["#", "Result", "Parameters / Message", "Layout", "View Layout"]
        )
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, result in enumerate(results):
            table.setItem(row, 0, QTableWidgetItem(str(result.index)))
            status = QTableWidgetItem("PASS" if result.passed else "FAIL")
            status.setForeground(QColor("#16803c" if result.passed else "#c62828"))
            table.setItem(row, 1, status)
            details = ", ".join(f"{key}={value}" for key, value in result.parameters.items())
            table.setItem(row, 2, QTableWidgetItem(f"{details}\n{result.message}"))
            if result.layout_path:
                preview = self._thumbnail(result.preview_path)
                table.setCellWidget(row, 3, preview)
                button = QPushButton("View Layout")
                button.clicked.connect(
                    lambda checked=False, path=result.preview_path: self._show_large(path)
                )
                button.setEnabled(bool(result.preview_path and Path(result.preview_path).exists()))
                table.setCellWidget(row, 4, button)
                table.setRowHeight(row, 110)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _thumbnail(path: str) -> QLabel:
        label = QLabel("Preview unavailable")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumSize(150, 100)
        if path and Path(path).exists():
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                label.setPixmap(pixmap.scaled(
                    150, 100, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
        return label

    def _show_large(self, path: str) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(self, "View Layout", f"Unable to load layout preview:\n{path}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Layout Preview")
        dialog.resize(900, 650)
        layout = QVBoxLayout(dialog)
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setPixmap(pixmap)
        scroll = QScrollArea()
        scroll.setWidget(image)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
