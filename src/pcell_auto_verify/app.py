import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from .database import PDKDatabase
from .ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PCell Auto Verify")
    data_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    window = MainWindow(PDKDatabase(data_dir / "pdks.sqlite3"))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

