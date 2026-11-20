"""Generate or replay PCell layouts using the same EDA backends as the GUI."""

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from subprocess import TimeoutExpired

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from core import KLayoutVerifier
from core.domestic180_verification import run_extraction as run_domestic180_extraction
from core.models import GeneratedLayout
from core.nmos_extraction import run_mos_extraction
from core.process_console import capture_process_console
from core.sky130_inverter import INVERTER_NAME, inverter_pcell
from core.sky130_library import is_sky130a
from core.sky130_nmos import MOS_PCELL_NAMES
from core.test_points import automatic_test_points
from plugins import PluginRegistry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdk", required=True, type=Path, help="PDK directory")
    parser.add_argument("--pcell", help="PCell name as shown in the platform")
    parser.add_argument("--list", action="store_true", help="List the available PCells")
    parser.add_argument("--case", choices=("automatic", "default", "negative", "manual"),
                        help="Defaults to automatic for generation and default for replay")
    parser.add_argument("--set", dest="edits", action="append", default=[], metavar="KEY=VALUE",
                        help="Edit a Default value in manual mode; repeat as needed")
    parser.add_argument("--callback-only", action="store_true", help="Run parameter callbacks and save the native transcript")
    parser.add_argument("--gds", type=Path, help="Replay a GUI-generated VERIFY_TOP GDS")
    parser.add_argument("--checks", nargs="+", choices=("drc", "lvs", "rcx"),
                        help="Defaults to all checks supported for the selected PCell")
    parser.add_argument("--output", type=Path, default=PROJECT / "output" / "cli",
                        help="Directory in which a new run directory is created")
    return parser


def _manual_edits(pdk, cell, points, edits, *, replay, require_callback=False):
    point = points[0]
    editable = {field.name for field in cell.parameters if not (field.hidden or field.readonly)}
    for assignment in edits:
        name, separator, value = assignment.partition("=")
        if not separator or name not in editable:
            raise ValueError(f"Expected an editable PCell parameter as KEY=VALUE: {assignment}")
        if value.strip():
            point[name] = value
        else:
            point.pop(name, None)
        if replay:
            continue  # User supplies the effective parameters of the existing layout.
        result = KLayoutVerifier.evaluate_parameter_edit(pdk.path, cell, name, point)
        if result is None and require_callback:
            raise ValueError(f"No native callback declaration found for {cell.name}")
        if result:
            for key, effective in result["values"].items():
                if key not in editable:
                    continue
                if effective:
                    point[key] = effective
                else:
                    point.pop(key, None)
            editable = {key for key in editable if result["editable"].get(key, True)}
    return [point]


def _replay(gds: Path, output: Path, name: str, point: dict[str, str]) -> GeneratedLayout:
    gds = gds.expanduser().resolve(strict=True)
    target = output / f"{name}_0001.gds"
    shutil.copyfile(gds, target)
    for suffix in (".json", ".png"):
        companion = gds.with_suffix(suffix)
        if companion.is_file():
            shutil.copyfile(companion, target.with_suffix(suffix))
    preview = target.with_suffix(".png")
    return GeneratedLayout(1, point, "Replayed existing GDS", str(target),
                           str(preview) if preview.is_file() else "", "manual")


def _drc_outcome(result) -> str:
    if result.passed:
        return "PASS"
    if result.layout_path:
        layout = Path(result.layout_path)
        if any(report.is_file() for report in (
            layout.with_name(f"{layout.stem}_drc.txt"), layout.with_suffix(".lyrdb"),
        )):
            return "FAIL"
    return "ERROR"


def _run(args) -> int:
    pdk = PluginRegistry().import_path(args.pdk)
    sky130 = pdk.plugin == "open-pdks" and is_sky130a(pdk.name)
    domestic = pdk.plugin == "domestic180"
    cells = {cell.name: cell for cell in pdk.pcells}
    if sky130 and set(MOS_PCELL_NAMES).issubset(cells):
        cells[INVERTER_NAME] = inverter_pcell()
    if args.list:
        print("\n".join(sorted(cells)))
        return 0
    if args.pcell not in cells:
        raise ValueError("Choose an available PCell with --pcell. Use --list to see the names.")
    cell = cells[args.pcell]
    case = args.case or ("default" if args.gds else "automatic")
    if args.gds and case == "automatic":
        raise ValueError("Only one case can be selected when replaying a GDS")
    if args.callback_only and (case != "manual" or not args.edits or args.gds or args.checks):
        raise ValueError("--callback-only requires --case manual and --set, without --gds or --checks")
    if args.edits and case != "manual":
        raise ValueError("--set requires --case manual")
    can_extract = domestic or (sky130 and cell.name in (*MOS_PCELL_NAMES, INVERTER_NAME))
    checks = args.checks or (["drc", "lvs", "rcx"] if can_extract else ["drc"])
    if not can_extract and any(check != "drc" for check in checks):
        raise ValueError(f"{pdk.name}/{cell.name} supports DRC only")

    points = automatic_test_points(cell, is_sky130a=sky130, is_domestic180=domestic)
    if case == "negative":
        if len(points) != 2:
            raise ValueError(f"{pdk.name}/{cell.name} has no predefined negative case")
        points = points[1:]
    elif case != "automatic":
        points = points[:1]
    base = args.output.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=f"{cell.name}-", dir=base))
    if args.callback_only:
        log_path = output / "callback.log"
        print(f"Callback log: {log_path}")
        with log_path.open("w", encoding="utf-8") as log:
            def write(message):
                print(message)
                print(message, file=log, flush=True)

            with capture_process_console(write):
                points = _manual_edits(pdk, cell, points, args.edits, replay=False, require_callback=True)
            write("Effective parameters: " + json.dumps(points[0], ensure_ascii=False))
        return 0
    if args.edits:
        points = _manual_edits(pdk, cell, points, args.edits, replay=bool(args.gds))
    verifier = KLayoutVerifier(pdk.path, str(output))
    layouts = (
        [_replay(args.gds, output, cell.name, points[0])] if args.gds
        else verifier.generate_layouts(cell, points)
    )
    summary = {"pdk": pdk.name, "pcell": cell.name, "case": case, "points": []}
    for layout in layouts:
        intentionally_negative = case == "negative" or (case == "automatic" and layout.index == 2)
        summary["points"].append({
            **asdict(layout), "expected_drc": (
                None if case == "manual" else ("FAIL" if intentionally_negative else "PASS")
            ), "checks": {},
        })

    extract = run_domestic180_extraction if domestic else run_mos_extraction
    for check in dict.fromkeys(checks):
        if check == "drc":
            for point, result in zip(summary["points"], verifier.check_layouts(layouts), strict=True):
                point["checks"][check] = {"status": _drc_outcome(result), "details": result.message}
        else:
            for point, layout in zip(summary["points"], layouts, strict=True):
                result = extract(Path(pdk.path), layout, check)
                point["checks"][check] = asdict(result)

    succeeded = True
    for point in summary["points"]:
        statuses = []
        succeeded &= bool(point["layout_path"])
        for check, result in point["checks"].items():
            status = result["status"]
            expected = (point["expected_drc"] or "PASS") if check == "drc" else (
                "PASS_BASIC" if check == "rcx" else "PASS"
            )
            succeeded &= status == expected
            suffix = " (expected)" if expected == status == "FAIL" else ""
            statuses.append(f"{check.upper()} {status}{suffix}")
        print(f"#{point['index']} {point['layout_path'] or point['message']}: {', '.join(statuses)}")

    summary["matched_expectations"] = succeeded
    report = output / "summary.json"
    report.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Report: {report}")
    return 0 if succeeded else 1


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        return _run(args)
    except (OSError, ValueError, TimeoutExpired) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
