"""PDK 与 PCell 元数据的 SQLite 存储。"""

import json
import sqlite3
from pathlib import Path

from core import PCell, PDK, Parameter


class PDKDatabase:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS pdks (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
                plugin TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS pcells (
                id INTEGER PRIMARY KEY,
                pdk_id INTEGER NOT NULL REFERENCES pdks(id) ON DELETE CASCADE,
                name TEXT NOT NULL, source TEXT NOT NULL, parameters TEXT NOT NULL
            );
            """
        )

    def close(self) -> None:
        self.connection.close()

    def list_pdks(self) -> list[PDK]:
        result: list[PDK] = []
        rows = self.connection.execute(
            "SELECT id,name,path,plugin,active FROM pdks ORDER BY name"
        )
        for row in rows:
            pdk = PDK(row[0], row[1], row[2], row[3], bool(row[4]))
            cell_rows = self.connection.execute(
                "SELECT name,source,parameters FROM pcells "
                "WHERE pdk_id=? ORDER BY name",
                (pdk.id,),
            )
            for cell in cell_rows:
                parameters = [Parameter(**item) for item in json.loads(cell[2])]
                pdk.pcells.append(PCell(cell[0], cell[1], parameters))
            result.append(pdk)
        return result

    def import_pdk(self, pdk: PDK) -> int:
        with self.connection:
            self.connection.execute(
                "INSERT INTO pdks(name,path,plugin,active) VALUES(?,?,?,0) "
                "ON CONFLICT(path) DO UPDATE SET "
                "name=excluded.name, plugin=excluded.plugin",
                (pdk.name, pdk.path, pdk.plugin),
            )
            row = self.connection.execute(
                "SELECT id FROM pdks WHERE path=?", (pdk.path,)
            ).fetchone()
            if row is None:  # pragma: no cover - SQLite guarantees the inserted row
                raise RuntimeError("无法读取刚刚导入的 PDK。")
            pdk_id = int(row[0])
            self.connection.execute("DELETE FROM pcells WHERE pdk_id=?", (pdk_id,))
            for cell in pdk.pcells:
                payload = json.dumps(
                    [
                        {
                            "name": parameter.name,
                            "default": parameter.default,
                            "value_range": parameter.value_range,
                        }
                        for parameter in cell.parameters
                    ]
                )
                self.connection.execute(
                    "INSERT INTO pcells(pdk_id,name,source,parameters) VALUES(?,?,?,?)",
                    (pdk_id, cell.name, cell.source, payload),
                )
        return pdk_id

    def activate(self, pdk_id: int) -> None:
        with self.connection:
            self.connection.execute("UPDATE pdks SET active=0")
            self.connection.execute(
                "UPDATE pdks SET active=1 WHERE id=?", (pdk_id,)
            )

    def remove(self, pdk_id: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM pdks WHERE id=?", (pdk_id,))
