"""A small, self-contained GF180 MCU NMOS PCell."""

import pya


class GF180MCUANMOS(pya.PCellDeclarationHelper):
    """Draw a contacted, Metal1-connected NMOS using GF180 drawing layers."""

    def __init__(self):
        super().__init__()
        width = self.param(
            "width", self.TypeDouble, "Gate width (µm)", default=2.0
        )
        length = self.param(
            "length", self.TypeDouble, "Gate length (µm)", default=0.6
        )
        for value in (1.0, 2.0, 4.0):
            width.add_choice(f"{value:g} µm", value)
        for value in (0.2, 0.6, 1.0):
            length.add_choice(f"{value:g} µm", value)

    def coerce_parameters_impl(self):
        self.width = max(1.0, float(self.width))
        # Keep the intentionally out-of-rule 0.2 µm example constructible: it
        # should produce a layout and fail DRC, rather than fail instantiation.
        self.length = max(0.2, float(self.length))

    def display_text_impl(self):
        return f"GF180 NMOS W={self.width:g} µm L={self.length:g} µm"

    def produce_impl(self):
        dbu = self.layout.dbu

        def box(layer, left, bottom, right, top):
            self.cell.shapes(self.layout.layer(pya.LayerInfo(*layer))).insert(
                pya.Box(*(round(coordinate / dbu) for coordinate in (
                    left, bottom, right, top
                )))
            )

        # GF180 MCU drawing layers: COMP, Poly2, Nplus, Contact and Metal1.
        comp, poly2, nplus = (22, 0), (30, 0), (32, 0)
        contact, metal1 = (33, 0), (34, 0)
        half_width = self.width / 2.0
        half_length = self.length / 2.0
        diffusion_extension = 1.1
        active_left = -half_length - diffusion_extension
        active_right = half_length + diffusion_extension

        box(comp, active_left, -half_width, active_right, half_width)
        box(nplus, active_left - 0.16, -half_width - 0.16,
            active_right + 0.16, half_width + 0.16)
        box(poly2, -half_length, -half_width - 0.6,
            half_length, half_width + 0.6)

        # Contact cuts are kept away from the gate and enclosed by both active
        # and the source/drain Metal1 bars.
        cut = 0.22
        cut_half = cut / 2.0
        contact_x = half_length + 0.55
        pitch = 0.44
        rows = max(1, int((self.width - 0.24 - cut) // pitch) + 1)
        first_y = -(rows - 1) * pitch / 2.0
        for sign in (-1, 1):
            x = sign * contact_x
            box(metal1, x - 0.24, -half_width + 0.06,
                x + 0.24, half_width - 0.06)
            for row in range(rows):
                y = first_y + row * pitch
                box(contact, x - cut_half, y - cut_half,
                    x + cut_half, y + cut_half)
