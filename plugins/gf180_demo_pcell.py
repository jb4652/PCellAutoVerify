"""A minimal, intentionally conservative demonstration PCell for gf180mcuA."""

import pya


class GF180MCUADemoRectangle(pya.PCellDeclarationHelper):
    """Draw one large Metal1 rectangle using dimensions expressed in microns."""

    def __init__(self):
        super().__init__()
        width = self.param(
            "width",
            self.TypeDouble,
            "Width (µm)",
            default=20.0,
        )
        height = self.param(
            "height",
            self.TypeDouble,
            "Height (µm)",
            default=20.0,
        )
        for declaration in (width, height):
            declaration.add_choice("10 µm", 10.0)
            declaration.add_choice("20 µm", 20.0)
            declaration.add_choice("40 µm", 40.0)

    def coerce_parameters_impl(self):
        # Keep programmatic callers safe as well as users of KLayout's dialog.
        self.width = max(10.0, float(self.width))
        self.height = max(10.0, float(self.height))

    def display_text_impl(self):
        return f"Demo Metal1 rectangle {self.width:g} × {self.height:g} µm"

    def produce_impl(self):
        # gf180mcuA's Metal1 drawing purpose is GDS layer/datatype 34/0.
        metal1 = self.layout.layer(pya.LayerInfo(34, 0))
        half_width = round(self.width / self.layout.dbu / 2.0)
        half_height = round(self.height / self.layout.dbu / 2.0)
        self.cell.shapes(metal1).insert(
            pya.Box(-half_width, -half_height, half_width, half_height)
        )
