"""Compose a four-port Sky130A inverter from the registered MOS PCells."""

import math
from pathlib import Path

from .models import PCell, Parameter
from .sky130_library import SKY130_PYTHON_PATH
from .sky130_nmos import instantiate_library_mos, load_mos_library


INVERTER_NAME = "cmos_inverter"
INVERTER_PORTS = ("A", "Y", "VDD", "VSS")
INVERTER_MODELS = ("sky130_fd_pr__nfet_01v8", "sky130_fd_pr__pfet_01v8")
_DEFAULTS = {"wn": 0.42, "ln": 0.15, "wp": 0.42, "lp": 0.15}


def inverter_pcell() -> PCell:
    return PCell(
        INVERTER_NAME, str(Path(__file__).resolve()),
        [Parameter(name, str(value), description="Channel dimension in µm")
         for name, value in _DEFAULTS.items()],
        str(SKY130_PYTHON_PATH),
    )


def _grid(value: float) -> int:
    """Snap coordinates to the 5 nm manufacturing grid at dbu=1 nm."""
    return int(round(value / 5)) * 5


def _terminals(layout, cell, gate_on_top: bool):
    import klayout.db as kdb

    metal = kdb.Region(cell.begin_shapes_rec(layout.layer(68, 20))).merged()
    pads = sorted((shape.bbox() for shape in metal.each()), key=lambda box: box.center().y)
    if len(pads) != 3:
        raise ValueError("The inverter expects three isolated Metal1 pads on each single-finger MOS")
    gate = pads.pop(-1 if gate_on_top else 0)
    source, drain = sorted(pads, key=lambda box: box.center().x)
    return tuple((_grid(box.center().x), _grid(box.center().y)) for box in (source, drain, gate))


def instantiate_inverter(layout, python_dir: Path, overrides: dict):
    import klayout.db as kdb

    dimensions = {**_DEFAULTS, **overrides}
    for name, minimum in _DEFAULTS.items():
        value = float(dimensions[name])
        if not math.isfinite(value) or value < minimum:
            raise ValueError(f"{name} must be at least {minimum} µm")
        if not math.isclose(value * 1000, _grid(value * 1000), abs_tol=1e-8):
            raise ValueError(f"{name} must be on the 0.005 µm manufacturing grid")
        dimensions[name] = value

    library = load_mos_library(python_dir)
    nfet, nmeta = instantiate_library_mos(layout, library, "nfet", {
        "w": dimensions["wn"], "l": dimensions["ln"], "nf": 1, "type": INVERTER_MODELS[0], "bulk": "None", "gate_con_pos": "top",
    })
    pfet, pmeta = instantiate_library_mos(layout, library, "pfet", {
        "w": dimensions["wp"], "l": dimensions["lp"], "nf": 1, "type": INVERTER_MODELS[1], "bulk": "None", "gate_con_pos": "bottom",
    })
    top = layout.create_cell("VERIFY_TOP")
    dy = _grid(nfet.bbox().top - pfet.bbox().bottom + 1800)
    top.insert(kdb.CellInstArray(nfet.cell_index(), kdb.Trans()))
    top.insert(kdb.CellInstArray(pfet.cell_index(), kdb.Trans(0, dy)))
    ns, nd, ng = _terminals(layout, nfet, True)
    ps, pd, pg = ((x, y + dy) for x, y in _terminals(layout, pfet, False))

    def box(layer, left, bottom, right, upper):
        top.shapes(layout.layer(*layer)).insert(kdb.Box(left, bottom, right, upper))

    def metal(start, end):
        x1, y1 = start
        x2, y2 = end
        if x1 != x2 and y1 != y2:
            raise ValueError("Inverter routing segments must be Manhattan")
        half = 145
        box((68, 20), min(x1, x2) - half, min(y1, y2) - half,
            max(x1, x2) + half, max(y1, y2) + half)

    def port(name, x, y):
        top.shapes(layout.layer(68, 16)).insert(kdb.Text(name, kdb.Trans(x, y)))

    left = min(nfet.bbox().left, pfet.bbox().left) - 1100
    right = max(nfet.bbox().right, pfet.bbox().right) + 700
    mid = _grid((ng[1] + pg[1]) / 2)
    for gate in (ng, pg):
        metal(gate, (gate[0], mid))
    metal((left, mid), (max(ng[0], pg[0]), mid))
    port("A", left, mid)
    for drain in (nd, pd):
        metal(drain, (right, drain[1]))
    metal((right, nd[1]), (right, pd[1]))
    port("Y", right, mid)

    for source, supply, implant in ((ns, "VSS", (94, 20)), (ps, "VDD", (93, 44))):
        y = source[1]
        for layer, half in (((65, 44), 230), (implant, 355), ((66, 44), 85),
                            ((67, 20), 215), ((67, 44), 85)):
            box(layer, left - half, y - half, left + half, y + half)
        metal((left, y), source)
        port(supply, left, y)

    well = pfet.bbox()
    box((64, 20), left - 650, min(well.bottom + dy, ps[1] - 650),
        well.right, max(well.top + dy, ps[1] + 650))

    return top, {"pdk": "sky130A", "pcell": INVERTER_NAME, "actual": dimensions,
                 "devices": [nmeta["actual"], pmeta["actual"]]}
