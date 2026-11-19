"""Summarize an extracted NMOS SPICE netlist."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.nmos_extraction import summarize_rcx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spice", nargs="?", type=Path, default=Path("output/rcx/nmos_rcx.spice"))
    parser.add_argument("--model", default="sky130_fd_pr__nfet_01v8")
    args = parser.parse_args()
    try:
        status, details = summarize_rcx(args.spice, args.model)
    except OSError as error:
        print(error, file=sys.stderr)
        print("RCX_RESULT=ERROR")
        return 2
    print(details)
    print(f"RCX_RESULT={status}")
    return 0 if status == "PASS_BASIC" else 1


if __name__ == "__main__":
    raise SystemExit(main())
