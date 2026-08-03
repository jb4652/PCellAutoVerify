import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget

from core import PCell, VerificationResult
from gui.results_dialog import VerificationResultsDialog


def test_failed_result_displays_layout_thumbnail_and_view_button(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    layout = tmp_path / "failed.gds"
    layout.write_text("layout", encoding="utf-8")
    preview = tmp_path / "failed.png"
    image = QImage(320, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("#336699"))
    assert image.save(str(preview))
    result = VerificationResult(
        1, {"width": "2"}, False, "DRC found 1 violation(s)",
        str(layout), str(preview),
    )

    dialog = VerificationResultsDialog(PCell("Device", "device.py"), [result])
    table = dialog.findChild(QTableWidget)

    assert table.columnCount() == 5
    assert table.horizontalHeaderItem(3).text() == "Layout"
    assert table.horizontalHeaderItem(4).text() == "View Layout"
    thumbnail = table.cellWidget(0, 3)
    assert isinstance(thumbnail, QLabel)
    assert thumbnail.pixmap() is not None
    button = table.cellWidget(0, 4)
    assert isinstance(button, QPushButton)
    assert button.isEnabled()

    dialog.close()
    app.processEvents()
