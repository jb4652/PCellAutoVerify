"""Generated test points and their GDS layout previews."""

import shutil
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QShowEvent, QWheelEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGraphicsScene,
    QGraphicsView,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import PCell
from core.models import GeneratedLayout
from core.process_console import command_entry


class LayoutPreviewView(QGraphicsView):
    def __init__(self, pixmap: QPixmap, parent=None) -> None:
        super().__init__(parent)
        scene = QGraphicsScene(self)
        item = scene.addPixmap(pixmap)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._image_rect = item.boundingRect()
        margin = max(pixmap.width(), pixmap.height())
        scene.setSceneRect(self._image_rect.adjusted(-margin, -margin, margin, margin))
        self.setScene(scene)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._fit_scale = 0.0

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._fit_scale:
            self.fitInView(self._image_rect, Qt.AspectRatioMode.KeepAspectRatio)
            self._fit_scale = self.transform().m11()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta and self._fit_scale:
            current = self.transform().m11()
            factor = 1.2 ** (max(-1200, min(1200, delta)) / 120)
            target = max(self._fit_scale / 2, min(current * factor, self._fit_scale * 16))
            cursor = event.position().toPoint()
            anchor = self.mapToScene(cursor)
            self.scale(target / current, target / current)
            offset = anchor - self.mapToScene(cursor)
            self.centerOn(self.mapToScene(self.viewport().rect().center()) + offset)
        event.accept()


class TestPointsDialog(QDialog):
    def __init__(
        self, pcell: PCell, points: list[GeneratedLayout], parent=None, *, write_console=None
    ) -> None:
        super().__init__(parent)
        self.write_console = write_console
        self.setWindowTitle(f"Test Points — {pcell.name}")
        self.resize(1000, 480)

        layout = QVBoxLayout(self)
        has_negative_case = any("metal1_test_width" in point.parameters for point in points)
        test_columns = ["Expected DRC", "Metal1 test width (µm)"] if has_negative_case else []
        table = QTableWidget(len(points), len(pcell.parameters) + 4 + len(test_columns))
        table.setHorizontalHeaderLabels(
            ["Point", "Layout", "View Layout", "Generation", *test_columns, *[p.name for p in pcell.parameters]]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, point in enumerate(points):
            label = f"VP-{point.index:03d}"
            if point.origin == "manual":
                label += " · Manual"
            table.setItem(row, 0, QTableWidgetItem(label))
            status = QTableWidgetItem(point.message.splitlines()[-1] if point.message else "")
            status.setToolTip(point.message)
            table.setItem(row, 3, status)
            if point.layout_path:
                self._add_layout(table, row, point)
            if has_negative_case:
                width = point.parameters.get("metal1_test_width")
                expected = "—" if point.origin == "manual" else ("FAIL" if width else "PASS")
                table.setItem(row, 4, QTableWidgetItem(expected))
                table.setItem(row, 5, QTableWidgetItem(width or "—"))
            for column, parameter in enumerate(pcell.parameters, 4 + len(test_columns)):
                table.setItem(
                    row, column, QTableWidgetItem(point.parameters.get(parameter.name, parameter.default))
                )
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(3, 170)
        layout.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_layout(self, table: QTableWidget, row: int, point: GeneratedLayout) -> None:
        preview = self._thumbnail(point.preview_path)
        preview.setToolTip(point.layout_path)
        table.setCellWidget(row, 1, preview)
        button = QPushButton("View Layout")
        button.setToolTip(point.layout_path)
        button.setEnabled(Path(point.layout_path).is_file())
        button.clicked.connect(
            lambda: self._view_layout(point.layout_path, point.preview_path)
        )
        table.setCellWidget(row, 2, button)
        table.setRowHeight(row, 110)

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

    def _view_layout(self, path: str, preview: str) -> None:
        pixmap = QPixmap(preview) if preview else QPixmap()
        if pixmap.isNull():
            executable = shutil.which("klayout")
            if executable and self.write_console:
                self._launch_layout_viewer(executable, path)
                return
            if executable:
                started, _ = QProcess.startDetached(executable, [path])
                if started:
                    return
            self._open_layout_folder(path)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Layout Preview")
        dialog.resize(900, 650)
        layout = QVBoxLayout(dialog)
        layout.addWidget(LayoutPreviewView(pixmap, dialog))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()


    def _open_layout_folder(self, path: str) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent))):
            QMessageBox.warning(self, "View Layout", f"GDS file:\n{path}")

    def _launch_layout_viewer(self, executable: str, path: str) -> None:
        # The viewer can outlive the test points dialog.
        process = QProcess(self.parent() or self)
        write = self.write_console
        write(command_entry([executable, path]))

        def drain(reader, label):
            data = bytes(reader())
            if data:
                write(f"[KLayout {label}]\n{data.decode(errors='replace').rstrip()}")

        def finished(code, _status):
            drain(process.readAllStandardOutput, "stdout")
            drain(process.readAllStandardError, "stderr")
            write(f"[KLayout exit: {code}]")
            process.deleteLater()

        def failed(error):
            write(f"[KLayout process error: {process.errorString()}]")
            if error == QProcess.ProcessError.FailedToStart:
                self._open_layout_folder(path)
                process.deleteLater()

        process.readyReadStandardOutput.connect(lambda: drain(process.readAllStandardOutput, "stdout"))
        process.readyReadStandardError.connect(lambda: drain(process.readAllStandardError, "stderr"))
        process.finished.connect(finished)
        process.errorOccurred.connect(failed)
        process.start(executable, [path])
