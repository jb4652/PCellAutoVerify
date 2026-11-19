import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolBar

from core import KLayoutVerifier, PCell, PDK, Parameter, VerificationResult
from database import PDKDatabase
from gui import MainWindow
from plugins import PluginRegistry


def test_pcell_tree_follows_source_path_and_verify_emits(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        KLayoutVerifier,
        "verify",
        lambda self, cell, points: [
            VerificationResult(index, point, True, "DRC passed")
            for index, point in enumerate(points, 1)
        ],
    )
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
    toolbar_buttons = [
        action for action in toolbar.actions() if not action.isSeparator()
    ]
    assert all(not action.icon().isNull() for action in toolbar_buttons)

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
    default_item = window.parameters.item(0, 1)
    assert default_item.flags() & Qt.ItemFlag.ItemIsEditable
    default_item.setText("1.5")
    assert window.current_cells[0].parameters[0].default == "1.5"
    window.generate_points()
    assert window.verify_button.isEnabled()
    window.verify()

    assert requested[0][0].name == "NfetPCell"
    assert requested[0][1] == [{"w": "1.5"}]
    assert "1 passed, 0 failed" in window.output.toPlainText()

    window.close()
    database.close()
    app.processEvents()


def test_sky130a_reimport_shows_registered_names_and_sources(tmp_path: Path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    pdk_root = tmp_path / "PDK installs" / "sky130A"
    package = pdk_root / "libs.tech/klayout/python/cells"
    package.mkdir(parents=True)
    (package / "devices.py").write_text(
        """
import klayout.db as kdb

class UnregisteredPCell(kdb.PCellDeclarationHelper):
    pass

class Device(kdb.PCellDeclarationHelper):
    def __init__(self):
        super().__init__()
        width = self.param("width", self.TypeDouble, "Width", default=0.6)
        width.add_choice("Narrow", 0.2)
        width.add_choice("Wide", 0.6)
        self.param("length", self.TypeDouble, "Length", default=1.0)
        self.param("area", self.TypeDouble, "Area", readonly=True, default=2.0)
        self.param("internal", self.TypeInt, "Internal", hidden=True, default=1)
""",
        encoding="utf-8",
    )
    (package / "__init__.py").write_text(
        """
import klayout.db as kdb
from .devices import Device

class sky130(kdb.Library):
    def __init__(self):
        super().__init__()
        for index in reversed(range(18)):
            self.layout().register_pcell(f"device_{index:02}", Device())
        self.register("sky130")
""",
        encoding="utf-8",
    )
    path = str(pdk_root)
    database = PDKDatabase(tmp_path / "gui.sqlite")
    legacy = PDK(
        None, "sky130A", path, "open-pdks",
        pcells=[PCell("UnregisteredPCell", "libs.tech/klayout/python/cells/__init__.py")],
    )
    pdk_id = database.import_pdk(legacy)
    database.activate(pdk_id)

    alias = tmp_path / "installation alias"
    alias.symlink_to(pdk_root, target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    pdk = PluginRegistry().import_path(Path(alias.name))
    assert pdk.path == str(pdk_root)
    assert database.import_pdk(pdk) == pdk_id
    assert len(database.list_pdks()) == 1
    imported_cell = database.list_pdks()[0].pcells[0]
    assert imported_cell.library_path == str(Path("libs.tech/klayout/python"))
    assert imported_cell.source == str(Path("libs.tech/klayout/python/cells/devices.py"))
    window = MainWindow(database)
    try:
        root = window.cells.topLevelItem(0)
        assert root.text(0) == "sky130A"
        assert root.isExpanded()
        assert [root.child(i).text(0) for i in range(root.childCount())] == [
            f"device_{index:02} (devices.py)"
            for index in range(18)
        ]
        assert root.child(0).toolTip(0) == str(package / "devices.py")
        window.cells.setCurrentItem(root.child(0))
        assert window.parameters.rowCount() == 4
        assert window.parameters.item(0, 0).text() == "width"
        assert window.parameters.item(0, 0).toolTip() == "Width"
        assert window.parameters.item(0, 1).text() == "0.6"
        assert window.parameters.item(0, 2).text() == "choices=[0.2, 0.6]"
        assert window.parameters.item(1, 2).text() == ""
        for row, name in ((2, "area"), (3, "internal")):
            assert window.parameters.item(row, 0).text() == name
            assert not window.parameters.item(row, 1).flags() & Qt.ItemFlag.ItemIsEditable
        window.generate_points()
        assert window.test_points[0] == [{"width": "0.6", "length": "1.0"}]
    finally:
        window.close()
        database.close()
        app.processEvents()
