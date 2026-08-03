import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolBar

from core import PCell, PDK, Parameter
from database import PDKDatabase
from gui import MainWindow


def test_pcell_tree_follows_source_path_and_verify_emits(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    database = PDKDatabase(tmp_path / "gui.sqlite")
    pdk_id = database.import_pdk(
        PDK(
            None,
            "sky130",
            "/pdk/sky130",
            "open-pdks",
            pcells=[
                PCell(
                    "NfetPCell",
                    "libs.tech/klayout/device.py",
                    [Parameter("w", "1", "1..2")],
                )
            ],
        )
    )
    database.activate(pdk_id)
    window = MainWindow(database)

    assert [action.text() for action in window.menuBar().actions()] == [
        "&File",
        "&Verification",
        "&View",
        "&Help",
    ]
    toolbar = window.findChild(QToolBar, "verificationToolbar")
    assert toolbar is not None
    assert "Run Verify" in [action.text() for action in toolbar.actions()]

    root = window.cells.topLevelItem(0)
    assert root.text(0) == "sky130"
    assert root.isExpanded()
    directory = root.child(0)
    assert directory.text(0) == "libs.tech"
    assert directory.isExpanded()
    file_item = directory.child(0).child(0)
    assert file_item.text(0) == "device.py"
    cell_item = file_item.child(0)
    assert cell_item.text(0) == "NfetPCell"
    assert cell_item.data(0, Qt.ItemDataRole.UserRole) == 0

    requested = []
    window.verification_requested.connect(
        lambda cell, points: requested.append((cell, points))
    )
    window.cells.setCurrentItem(cell_item)
    assert window.generate_action.isEnabled()
    window.generate_points()
    assert window.verify_button.isEnabled()
    window.verify()

    assert requested[0][0].name == "NfetPCell"
    assert len(requested[0][1]) == 2
    assert "Verification requested" in window.output.toPlainText()

    window.close()
    database.close()
    app.processEvents()
