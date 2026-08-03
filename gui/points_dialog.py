"""测试点预览对话框。"""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import PCell


class TestPointsDialog(QDialog):
    def __init__(
        self, pcell: PCell, points: list[dict[str, str]], parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Test Points — {pcell.name}")
        self.resize(760, 480)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{len(points)} generated test point(s)"))
        table = QTableWidget(len(points), len(pcell.parameters))
        table.setHorizontalHeaderLabels(
            [parameter.name for parameter in pcell.parameters]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, point in enumerate(points):
            for column, parameter in enumerate(pcell.parameters):
                table.setItem(
                    row, column, QTableWidgetItem(point.get(parameter.name, ""))
                )
        layout.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
