"""QApplication 的创建及应用级依赖装配。"""

import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from database import PDKDatabase
from gui import MainWindow


def default_database_path() -> Path:
    data_location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    return Path(data_location) / "pdks.sqlite3"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PCell Auto Verify")
    database = PDKDatabase(default_database_path())
    window = MainWindow(database)
    window.show()
    exit_code = app.exec()
    database.close()
    return exit_code
