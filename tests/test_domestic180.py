from pathlib import Path

from klayout import db as kdb

from core import KLayoutVerifier
from core.domestic180_verification import run_extraction
from core.test_points import default_test_point
from pdks.domestic180.pcells import PIN
from plugins import PluginRegistry


def test_bundled_pdk_import_and_geometry_verification(tmp_path: Path):
    root = Path(__file__).resolve().parents[1] / "pdks/domestic180"
    pdk = PluginRegistry().import_path(root)
    assert {cell.name for cell in pdk.pcells} == {"nmos", "pmos", "inverter"}
    nmos = next(cell for cell in pdk.pcells if cell.name == "nmos")
    callback = KLayoutVerifier.evaluate_parameter_edit(
        pdk.path, nmos, "l", {**default_test_point(nmos), "l": "0.15"},
    )
    assert callback["values"]["l"] == "0.18"
    for cell in pdk.pcells:
        verifier = KLayoutVerifier(pdk.path, str(tmp_path / cell.name))
        defaults = default_test_point(cell)
        points = verifier.generate_layouts(cell, [defaults, {**defaults, "metal_width": "0.12"}])
        assert all(point.layout_path for point in points), points
        assert [result.passed for result in verifier.check_layouts(points)] == [True, False]
        assert run_extraction(root, points[0], "lvs").status == "PASS"
        rcx = run_extraction(root, points[0], "rcx")
        assert rcx.status == "PASS_BASIC"
        assert rcx.rcx.mos == (2 if cell.name == "inverter" else 1)
        assert rcx.rcx.resistors == rcx.rcx.capacitors == 4

        # Corrupt only the generated GDS to check isolation from the reference parameters.
        layout = kdb.Layout()
        layout.read(points[0].layout_path)
        layout.clear_layer(layout.find_layer(*PIN))
        layout.write(points[0].layout_path)
        assert run_extraction(root, points[0], "lvs").status == "FAIL"
