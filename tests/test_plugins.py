from pathlib import Path

import pytest

from core import generate_test_points
from plugins import PluginRegistry


def test_open_pdks_scans_klayout_style_pcell(tmp_path: Path):
    root = tmp_path / "sky130"
    root.mkdir()
    (root / "device.py").write_text(
        "class NfetPCell(PCellDeclarationHelper):\n"
        "    width = 1.0\n"
        "    def __init__(self):\n"
        "        self.param('length', TypeDouble, 'Length', default=0.15, min=0.1, max=10)\n"
        "    def produce_impl(self): pass\n",
        encoding="utf-8",
    )
    pdk = PluginRegistry().import_path(root)
    assert pdk.plugin == "open-pdks"
    assert pdk.pcells[0].name == "NfetPCell"
    width = next(parameter for parameter in pdk.pcells[0].parameters if parameter.name == "width")
    assert width.default == "1.0"
    length = next(parameter for parameter in pdk.pcells[0].parameters if parameter.name == "length")
    assert length.default == "0.15"
    assert length.value_range == "min=0.1, max=10"


def test_open_pdks_does_not_turn_dynamic_defaults_into_empty_strings(tmp_path: Path):
    root = tmp_path / "gf180mcu"
    root.mkdir()
    (root / "cap_mim.py").write_text(
        "class MimCap(PCellDeclarationHelper):\n"
        "    def __init__(self):\n"
        "        self.param('w', self.TypeDouble, 'Width', default=rules.mim_w)\n"
        "    def coerce_parameters_impl(self): pass\n",
        encoding="utf-8",
    )

    width = PluginRegistry().import_path(root).pcells[0].parameters[0]

    assert width.default == ""
    assert width.value_range == ""


def test_unsupported_directory_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="没有插件支持"):
        PluginRegistry().import_path(tmp_path)


def test_gf180mcua_import_adds_an_nmos_starter_pcell(tmp_path: Path):
    root = tmp_path / "gf180mcuA"
    root.mkdir()

    pdk = PluginRegistry().import_path(root)

    nmos = pdk.pcells[0]
    assert nmos.name == "GF180MCUANMOS"
    assert Path(nmos.source).is_absolute()
    assert Path(nmos.source).is_file()
    values = [
        (parameter.name, parameter.default, parameter.value_range)
        for parameter in nmos.parameters
    ]
    assert values == [
        ("width", "2.0", "choices=[1.0, 2.0, 4.0]"),
        ("length", "0.6", "choices=[0.2, 0.6, 1.0]"),
    ]
    points = generate_test_points(nmos)
    assert len(points) == 4
    assert sum(point["length"] == "0.2" for point in points) == 2


def test_starter_pcell_is_not_added_to_other_gf180_imports(tmp_path: Path):
    root = tmp_path / "gf180mcuB"
    root.mkdir()

    pdk = PluginRegistry().import_path(root)

    assert all(cell.name != "GF180MCUANMOS" for cell in pdk.pcells)
