"""Detailed DRC results with layout previews and a printable PDF report."""

import html
import shutil
from pathlib import Path

from PySide6.QtCore import QTemporaryDir, Qt
from PySide6.QtGui import QColor, QPageSize, QPdfWriter, QPixmap, QTextDocument
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHeaderView, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from core import PCell, VerificationResult


class VerificationResultsDialog(QDialog):
    def __init__(self, pcell: PCell, results: list[VerificationResult], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"DRC Results — {pcell.name}")
        self.resize(980, 560)
        layout = QVBoxLayout(self)
        report_bar = QHBoxLayout()
        self.pdf_button = QPushButton("View PDF Report")
        self.pdf_button.setObjectName("viewPdfReportButton")
        report_bar.addWidget(self.pdf_button)
        report_bar.addStretch()
        layout.addLayout(report_bar)

        self._report_directory = QTemporaryDir()
        self._report_path = Path(self._report_directory.path()) / f"{pcell.name}_drc_report.pdf"
        self._create_pdf_report(pcell, results, self._report_path)
        self.pdf_button.setEnabled(self._report_path.exists())
        self.pdf_button.clicked.connect(self._show_pdf_report)

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
    def _create_pdf_report(
        pcell: PCell, results: list[VerificationResult], destination: Path
    ) -> None:
        """Render a portable summary using Qt's own PDF writer."""
        passed = sum(result.passed for result in results)
        rows = []
        for result in results:
            parameters = ", ".join(
                f"{key}={value}" for key, value in result.parameters.items()
            ) or "—"
            rows.append(
                "<tr>"
                f"<td>{result.index}</td>"
                f"<td class=\"{'pass' if result.passed else 'fail'}\">"
                f"{'PASS' if result.passed else 'FAIL'}</td>"
                f"<td>{html.escape(parameters)}</td>"
                f"<td>{html.escape(result.message)}</td>"
                "</tr>"
            )
        document = QTextDocument()
        document.setHtml(
            "<style>"
            "body { font-family: sans-serif; color: #222; }"
            "h1 { color: #24364b; }"
            "table { border-collapse: collapse; width: 100%; }"
            "th, td { border: 1px solid #aaa; padding: 6px; }"
            "th { background: #e8edf3; }"
            ".pass { color: #16803c; font-weight: bold; }"
            ".fail { color: #c62828; font-weight: bold; }"
            "</style>"
            f"<h1>DRC Report — {html.escape(pcell.name)}</h1>"
            f"<p><b>Summary:</b> {passed} passed, {len(results) - passed} failed, "
            f"{len(results)} total.</p>"
            "<table><thead><tr><th>#</th><th>Result</th><th>Parameters</th>"
            f"<th>Message</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
        writer = QPdfWriter(str(destination))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setTitle(f"DRC Report — {pcell.name}")
        writer.setCreator("PCell Auto Verify")
        document.print_(writer)

    def _show_pdf_report(self) -> None:
        if not self._report_path.exists():
            QMessageBox.warning(self, "PDF Report", "The PDF report is unavailable.")
            return
        PdfReportDialog(self._report_path, self).exec()

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


class PdfReportDialog(QDialog):
    """Display a report with Qt PDF and allow the user to save a copy."""

    def __init__(self, report_path: Path, parent=None):
        super().__init__(parent)
        self.report_path = report_path
        self.setWindowTitle("DRC PDF Report")
        self.resize(950, 720)
        layout = QVBoxLayout(self)

        self.document = QPdfDocument(self)
        self.document.load(str(report_path))
        self.viewer = QPdfView(self)
        self.viewer.setObjectName("pdfReportViewer")
        self.viewer.setDocument(self.document)
        self.viewer.setPageMode(QPdfView.PageMode.MultiPage)
        self.viewer.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        layout.addWidget(self.viewer)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.save_button = buttons.addButton(
            "Save PDF", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.save_button.setObjectName("savePdfReportButton")
        self.save_button.clicked.connect(self._save_pdf)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_pdf(self) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Save DRC PDF Report",
            self.report_path.name,
            "PDF files (*.pdf)",
        )
        if not destination:
            return
        destination_path = Path(destination)
        if destination_path.suffix.lower() != ".pdf":
            destination_path = destination_path.with_suffix(".pdf")
        try:
            shutil.copyfile(self.report_path, destination_path)
        except OSError as error:
            QMessageBox.warning(self, "Save PDF", f"Unable to save the report:\n{error}")
