"""Abstract 180 nm CMOS geometry for the domestic180 PDK."""

from klayout import db as kdb

N_ACTIVE = (1, 0)
P_ACTIVE = (2, 0)
GATE = (3, 0)
CONTACT = (4, 0)
METAL = (5, 0)
N_BODY = (6, 0)
P_BODY = (7, 0)
PIN = (5, 16)


class MosGeometry:
    """Place devices and route their contacts on the domestic180 layer stack."""

    def __init__(self, layout, cell, metal_width):
        self.layout = layout
        self.cell = cell
        self.half_width = self.units(metal_width) // 2

    def units(self, value):
        return round(value / self.layout.dbu)

    def box(self, layer, left, bottom, right, top):
        self.cell.shapes(self.layout.layer(*layer)).insert(kdb.Box(left, bottom, right, top))

    def square(self, layer, point, half):
        x, y = point
        self.box(layer, x - half, y - half, x + half, y + half)

    def wire(self, start, end):
        x1, y1 = start
        x2, y2 = end
        h = self.half_width
        self.box(METAL, min(x1, x2) - h, min(y1, y2) - h, max(x1, x2) + h, max(y1, y2) + h)

    def pin(self, name, point):
        self.cell.shapes(self.layout.layer(*PIN)).insert(kdb.Text(name, kdb.Trans(*point)))

    def device(self, polarity, width, length, center_y, gate_up):
        x, half_width = self.units(1.5), self.units(width) // 2
        left = x - self.units(length) // 2
        right = left + self.units(length)
        bottom, top = center_y - half_width, center_y - half_width + self.units(width)
        gate_y = top + self.units(0.5) if gate_up else bottom - self.units(0.5)
        self.box(N_ACTIVE if polarity == "n" else P_ACTIVE,
                 left - self.units(0.8), bottom, right + self.units(0.8), top)
        self.box(GATE, left, min(bottom - self.units(0.15), gate_y - self.units(0.12)),
                 right, max(top + self.units(0.15), gate_y + self.units(0.12)))
        pads = {
            "S": (left - self.units(0.4), center_y),
            "D": (right + self.units(0.4), center_y),
            "G": (x, gate_y),
            "B": (left - self.units(1.4), center_y),
        }
        self.square(N_BODY if polarity == "n" else P_BODY, pads["B"], self.units(0.2))
        for point in pads.values():
            self.square(CONTACT, point, self.units(0.06))
            self.square(METAL, point, self.half_width)
        return pads


class _MosPCell(kdb.PCellDeclarationHelper):
    dimensions = {}
    polarity = ""

    def __init__(self):
        super().__init__()
        for name, minimum in self.dimensions.items():
            default = 0.60 if "w" in name else minimum
            self.param(name, self.TypeDouble, name.upper(), default=default, unit="µm")
        self.param("metal_width", self.TypeDouble, "Metal1 route and pad width", default=0.30, unit="µm")

    def coerce_parameters_impl(self):
        for name, minimum in self.dimensions.items():
            setattr(self, name, max(minimum, round(float(getattr(self, name)) / 0.005) * 0.005))
        # Widths below the rule remain available for DRC regression cases.
        self.metal_width = max(0.12, round(float(self.metal_width) / 0.005) * 0.005)

    def produce_impl(self):
        geometry = MosGeometry(self.layout, self.cell, self.metal_width)
        for name, position in geometry.device(self.polarity, self.w, self.l, 0, True).items():
            geometry.pin(name, position)


class nmos(_MosPCell):
    dimensions = {"w": 0.42, "l": 0.18}
    polarity = "n"


class pmos(_MosPCell):
    dimensions = {"w": 0.42, "l": 0.18}
    polarity = "p"


class inverter(_MosPCell):
    dimensions = {"wn": 0.42, "ln": 0.18, "wp": 0.42, "lp": 0.18}

    def produce_impl(self):
        g = MosGeometry(self.layout, self.cell, self.metal_width)
        dy = g.units((self.wn + self.wp) / 2 + 2.0)
        n = g.device("n", self.wn, self.ln, 0, True)
        p = g.device("p", self.wp, self.lp, dy, False)
        # Space the output trunk beyond either device's drain pad.
        right = max(n["D"][0], p["D"][0]) + g.units(1.0)
        for device, supply in ((n, "VSS"), (p, "VDD")):
            g.wire(device["S"], device["B"])
            g.pin(supply, device["B"])
            g.wire(device["D"], (right, device["D"][1]))
        g.wire((right, 0), (right, dy))
        g.pin("Y", (right, dy // 2))
        g.wire(n["G"], p["G"])
        g.pin("A", (n["G"][0], (n["G"][1] + p["G"][1]) // 2))
