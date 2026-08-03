from pathlib import Path

import pytest

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


def test_unsupported_directory_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="没有插件支持"):
        PluginRegistry().import_path(tmp_path)
