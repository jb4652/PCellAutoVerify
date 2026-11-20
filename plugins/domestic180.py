"""Import the bundled domestic180 CMOS library."""

from pathlib import Path

from core import PCell, PDK, Parameter
from core.domestic180_verification import is_domestic180
from core.process_console import write_process_console
from .base import PDKPlugin


class Domestic180Plugin(PDKPlugin):
    name = "domestic180"

    supports = staticmethod(is_domestic180)

    def scan(self, root: Path) -> PDK:
        if not (root / "pcells.py").is_file():
            raise ValueError("domestic180 requires pcells.py")
        cells = [
            PCell(name, "pcells.py", [
                *[Parameter(field, default) for field, default in dimensions],
                Parameter("metal_width", "0.30", description="Metal1 route width in µm"),
            ])
            for name, dimensions in (
                ("nmos", (("w", "0.60"), ("l", "0.18"))),
                ("pmos", (("w", "0.60"), ("l", "0.18"))),
                ("inverter", (("wn", "0.60"), ("ln", "0.18"), ("wp", "0.60"), ("lp", "0.18"))),
            )
        ]
        write_process_console(
            f"[domestic180 import]\nPDK: {root.resolve()}\nPCells: " + ", ".join(cell.name for cell in cells)
        )
        return PDK(None, "domestic180", str(root.resolve()), self.name, pcells=cells)
