"""Compatibility and layout generation for Sky130A MOS PCells."""

import json
import tempfile
from pathlib import Path

from .sky130_library import load_library


MOS_PCELL_NAMES = ("nfet", "pfet")


def nmos_defaults() -> dict[str, object]:
    path = Path(__file__).resolve().parents[1] / "config" / "sky130_nmos.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _transfer_component(component, target_cell):
    import klayout.db as kdb

    if target_cell is None:
        raise ValueError("Sky130A MOS PCell has no target cell")

    # Older gdsfactory releases cannot expose the component as a KLayout cell.
    with tempfile.TemporaryDirectory(prefix="sky130-mos-") as directory:
        path = Path(directory) / "component.gds"
        component.write_gds(str(path))
        source_layout = kdb.Layout()
        source_layout.read(str(path))
        source_cell = source_layout.top_cell()
        if source_cell is None or source_cell.bbox().empty():
            raise RuntimeError("Sky130A MOS component GDS is empty")

        target_layout = target_cell.layout()
        if abs(source_layout.dbu - target_layout.dbu) > 1e-12:
            raise RuntimeError(
                f"DBU mismatch: {source_layout.dbu} vs {target_layout.dbu}"
            )
        source_layout.scale_and_snap(source_cell, 5, mult=1, div=1)
        mapping = kdb.CellMapping()
        mapping.for_single_cell(target_cell, source_cell)
        target_cell.copy_tree_shapes(source_cell, mapping)


def instantiate_nmos(layout, python_dir: Path, overrides: dict):
    """Keep the standalone NMOS command on the shared MOS generation path."""
    return instantiate_mos(layout, python_dir, "nfet", overrides)


def instantiate_mos(layout, python_dir: Path, name: str, overrides: dict):
    """Instantiate the selected MOS PCell with the Sky130A compatibility fixes."""
    import kfactory as kf
    import kfactory.kcell as kc

    if not hasattr(kc, "_get_default_kcl"):
        kc._get_default_kcl = lambda: kf.kcl

    library = load_library(python_dir)
    from cells import draw_fet, pdk

    pdk.take_component = _transfer_component
    draw_fet.take_component = _transfer_component

    declaration = library.layout().pcell_declaration(name)
    if declaration is None:
        raise ValueError(f"The Sky130A library does not register {name}")

    definitions = declaration.get_parameters()
    params = {parameter.name: parameter.default for parameter in definitions}
    unknown = overrides.keys() - params.keys()
    if unknown:
        raise ValueError(f"Unsupported {name} parameters: {', '.join(sorted(unknown))}")

    defaults = nmos_defaults()
    requested = {
        name: defaults[name]
        for name in ("bulk", "gate_con_pos")
        if name in params and params[name] is None
    }
    requested.update(overrides)
    params.update(requested)
    layout.dbu = 0.001
    cell = layout.create_cell(name, library.name(), params)
    if cell is None:
        raise RuntimeError(f"KLayout could not instantiate the Sky130A {name}")
    errors = list(cell.shapes(layout.error_layer()).each())
    if errors:
        details = "\n".join(shape.text.string for shape in errors if shape.is_text())
        raise RuntimeError(details or f"KLayout reported a Sky130A {name} generation error")
    if cell.bbox().empty():
        raise RuntimeError(f"Sky130A {name} produced no geometry")

    actual = dict(zip(params, cell.pcell_parameters()))
    return cell, {
        "pdk": "sky130A",
        "device": actual.get("type"),
        "library": library.name(),
        "pcell": name,
        "requested": requested,
        "actual": actual,
    }


def write_metadata(output: Path, metadata: dict) -> None:
    output.with_suffix(".json").write_text(
        json.dumps({**metadata, "gds": str(output)}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
