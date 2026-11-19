import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QImage
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget

from core import PCell, VerificationResult
from core.models import GeneratedLayout
from gui.points_dialog import TestPointsDialog as PointsDialog
from gui.results_dialog import PdfReportDialog, VerificationResultsDialog


def test_generated_point_displays_layout_thumbnail_and_view_button(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    layout = tmp_path / "failed.gds"
    layout.write_text("layout", encoding="utf-8")
    preview = tmp_path / "failed.png"
    image = QImage(320, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("#336699"))
    assert image.save(str(preview))
    result = GeneratedLayout(
        1, {"width": "2"}, "GDS generated",
        str(layout), str(preview),
    )

    dialog = PointsDialog(PCell("Device", "device.py"), [result])
    table = dialog.findChild(QTableWidget)

    assert table.columnCount() == 4
    assert table.horizontalHeaderItem(1).text() == "Layout"
    assert table.horizontalHeaderItem(2).text() == "View Layout"
    thumbnail = table.cellWidget(0, 1)
    assert isinstance(thumbnail, QLabel)
    assert thumbnail.pixmap() is not None
    button = table.cellWidget(0, 2)
    assert isinstance(button, QPushButton)
    assert button.isEnabled()

    dialog.close()
    app.processEvents()


def test_results_dialog_creates_viewable_and_saveable_pdf_report(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    result = VerificationResult(
        1, {"width": "2<&"}, False, "DRC found <1> violation(s)"
    )
    dialog = VerificationResultsDialog(PCell("Device", "device.py"), [result])

    report_button = dialog.findChild(QPushButton, "viewPdfReportButton")
    assert report_button is not None
    assert report_button.isEnabled()
    assert dialog._report_path.exists()
    assert dialog._report_path.read_bytes().startswith(b"%PDF")

    viewer_dialog = PdfReportDialog(dialog._report_path, dialog)
    assert viewer_dialog.findChild(QPdfView, "pdfReportViewer") is not None
    save_button = viewer_dialog.findChild(QPushButton, "savePdfReportButton")
    assert save_button is not None
    assert save_button.text() == "Save PDF"

    viewer_dialog.close()
    dialog.close()
    app.processEvents()


def test_layout_button_remains_enabled_without_png(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    layout = tmp_path / "nfet.gds"
    layout.touch()
    result = GeneratedLayout(1, {}, "GDS generated", str(layout))
    dialog = PointsDialog(PCell("nfet", "fet.py"), [result])
    table = dialog.findChild(QTableWidget)
    button = table.cellWidget(0, 2)
    assert button.isEnabled()
    assert button.toolTip() == str(layout)
    dialog.close()
    app.processEvents()
