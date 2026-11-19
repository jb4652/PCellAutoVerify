"""Generate a Sky130A NMOS GDS and record its effective PCell parameters."""

import argparse
import sys
from pathlib import Path

import klayout.db as kdb

# Running this script by path puts scripts/, rather than the checkout, on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.sky130_nmos import instantiate_nmos, nmos_defaults, write_metadata
from core.sky130_library import find_sky130_python_dir


def main() -> None:
    defaults = nmos_defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdk", required=True, type=Path, help="Sky130A root, KLayout, or Python directory")
    parser.add_argument("--w", type=float, default=defaults["w"])
    parser.add_argument("--l", type=float, default=defaults["l"])
    parser.add_argument("--nf", type=int, default=defaults["nf"])
    parser.add_argument("--m", type=int, default=1, help="Multiplier recorded in JSON metadata")
    parser.add_argument("--output", type=Path, default=Path("output/nmos.gds"))
    args = parser.parse_args()
    python_dir = find_sky130_python_dir(args.pdk)
    if python_dir is None:
        parser.error(f"Sky130A cells/__init__.py not found under {args.pdk}")

    layout = kdb.Layout()
    cell, metadata = instantiate_nmos(
        layout,
        python_dir,
        {**defaults, "w": args.w, "l": args.l, "nf": args.nf},
    )
    top = layout.create_cell("NMOS_TOP")
    top.insert(kdb.CellInstArray(cell.cell_index(), kdb.Trans()))
    output = args.output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(output))
    write_metadata(output, {**metadata, "m": args.m})
    print(f"GDS: {output}")
    print(f"JSON: {output.with_suffix('.json')}")
    print(f"BBox: {top.bbox()}")


if __name__ == "__main__":
    main()
