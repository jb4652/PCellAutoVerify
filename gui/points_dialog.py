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

from core import PCell, inferred_range


class TestPointsDialog(QDialog):
    def __init__(
        self, pcell: PCell, points: list[dict[str, str]], parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Test Points — {pcell.name}")
        self.resize(760, 480)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f"{len(points)} concrete verification point(s) · "
                "values include boundaries and defaults"
            )
        )
        ranges = "  ·  ".join(
            f"{parameter.name}: {parameter.value_range or inferred_range(parameter) or 'default only'}"
            for parameter in pcell.parameters
        )
        range_label = QLabel(f"Parameter ranges — {ranges}")
        range_label.setWordWrap(True)
        layout.addWidget(range_label)
        table = QTableWidget(len(points), len(pcell.parameters) + 1)
        table.setHorizontalHeaderLabels(
            ["Point", *[parameter.name for parameter in pcell.parameters]]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, point in enumerate(points):
            table.setItem(row, 0, QTableWidgetItem(f"VP-{row + 1:03d}"))
            for column, parameter in enumerate(pcell.parameters):
                table.setItem(
                    row,
                    column + 1,
                    QTableWidgetItem(point.get(parameter.name, parameter.default)),
                )
        layout.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
