from pathlib import Path

from core import PCell, PDK, Parameter
from database import PDKDatabase


def test_round_trip_activate_and_remove(tmp_path: Path):
    database = PDKDatabase(tmp_path / "test.sqlite")
    first = PDK(None, "sky130", "/pdk/sky130", "open-pdks", pcells=[PCell("nfet", "nfet.py", [Parameter("w", "1.0", "0.4..10")])])
    second = PDK(None, "gf180", "/pdk/gf180", "open-pdks")
    first_id = database.import_pdk(first)
    second_id = database.import_pdk(second)
    database.activate(first_id)
    loaded = database.list_pdks()
    assert [p.name for p in loaded if p.active] == ["sky130"]
    assert loaded[1].pcells[0].parameters[0].name == "w"
    database.activate(second_id)
    assert [p.name for p in database.list_pdks() if p.active] == ["gf180"]
    database.remove(first_id)
    assert [p.name for p in database.list_pdks()] == ["gf180"]
