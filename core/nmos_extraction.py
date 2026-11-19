"""Sky130A MOS reference generation, LVS comparison, and RCX summaries."""

import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from .magic_drc import run_sky130_magic
from .models import GeneratedLayout
from .sky130_inverter import INVERTER_MODELS, INVERTER_NAME, INVERTER_PORTS
from .sky130_nmos import MOS_PCELL_NAMES


@dataclass(frozen=True, slots=True)
class RcxCounts:
    model: str
    mos: int
    resistors: int
    capacitors: int
    all_models_present: bool = True

    @property
    def status(self) -> str:
        return "PASS_BASIC" if self.mos and self.all_models_present else "FAIL"

    def describe(self) -> str:
        return (
            f"Expected MOS model: {self.model}\nMOS instances: {self.mos}\n"
            f"Resistors: {self.resistors}\nCapacitors: {self.capacitors}\n\n"
            "Basic check: verifies the expected MOS models. Zero resistor or capacitor counts are shown as extracted."
        )


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    index: int
    status: str
    details: str
    summary: str = ""
    rcx: RcxCounts | None = None


def _reference_spice(top: str, model: str, values: dict) -> str:
    width, length, fingers = (float(values[key]) for key in ("w", "l", "nf"))
    if not all(math.isfinite(value) and value > 0 for value in (width, length, fingers)):
        raise ValueError("Reference requires finite positive w, l, and nf")
    if not fingers.is_integer():
        raise ValueError("Reference requires an integer finger count")
    if values.get("bulk") not in (None, "None") or values.get("interdig"):
        raise ValueError("Automatic LVS reference supports MOS PCells without a bulk tie, guard ring, or interdigitation")

    # Plain multi-finger PCells share adjacent diffusion and expose independent gates.
    devices = [
        f"X{index} DIFF{index + 1} G{index} DIFF{index} B {model} w={width:g} l={length:g}"
        for index in range(int(fingers))
    ]
    return "\n".join(["* Reference from effective PCell parameters", f".subckt {top}", *devices, f".ends {top}", ""])


def _inverter_reference(top: str, devices: list[dict]) -> str:
    lines = [f".subckt {top} {' '.join(INVERTER_PORTS)}"]
    for device, supply, transistor in zip(devices, ("VSS", "VDD"), MOS_PCELL_NAMES, strict=True):
        width, length = (float(device[key]) for key in ("w", "l"))
        model = device["type"]
        if model != f"sky130_fd_pr__{transistor}_01v8" or device["nf"] != 1:
            raise ValueError("The inverter reference requires one standard 1.8 V MOS of each type")
        if not all(math.isfinite(dimension) and dimension > 0 for dimension in (width, length)):
            raise ValueError("Inverter reference requires positive finite dimensions")
        lines.append(f"X{transistor} Y A {supply} {supply} {model} w={width:g} l={length:g}")
    lines.append(f".ends {top}")
    return "\n".join(lines) + "\n"


def _compare_lvs(directory: Path, setup: Path, top: str, prefix: str = "nmos") -> tuple[str, str]:
    executable = shutil.which("netgen-lvs")
    if not executable:
        return "ERROR", "netgen-lvs executable not found"
    if not setup.is_file():
        return "ERROR", f"Netgen setup file not found: {setup}"

    # Netgen parses "filename cell" as a Tcl list. Local basenames also work
    # when the parent directory or PDK path contains whitespace.
    extracted = f"{prefix}_extracted.spice"
    reference = f"{prefix}_reference.spice"
    log = f"{prefix}_lvs.log"
    with TemporaryDirectory(prefix="netgen-", dir=directory) as scratch_dir:
        scratch = Path(scratch_dir)
        for name in (extracted, reference):
            shutil.copyfile(directory / name, scratch / name)
        try:
            completed = subprocess.run(
                [executable, "-batch", "lvs", f"{extracted} {top}",
                 f"{reference} {top}", str(setup), log],
                cwd=scratch, capture_output=True, text=True, errors="replace", timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return "ERROR", f"Netgen could not complete: {error}"

        console = completed.stdout + "\n" + completed.stderr
        (directory / "netgen.log").write_text(console, encoding="utf-8")
        report = scratch / log
        if completed.returncode or not report.is_file():
            return "ERROR", f"Netgen did not produce an LVS report\n{console.strip()[-1600:]}"
        content = report.read_text(encoding="utf-8", errors="replace")
        report.replace(directory / report.name)

    if re.search(r"property errors|do not match|failed to match|pin lists are not equivalent", content, re.I):
        return "FAIL", content
    if re.search(r"^Circuits match uniquely\.", content, re.M):
        return "PASS", content
    return "ERROR", f"Netgen did not report a conclusive comparison\n{content}"


def _count_rcx(spice: Path, models: tuple[str, ...]) -> RcxCounts:
    text = spice.read_text(encoding="utf-8", errors="replace")
    model_counts = dict.fromkeys((model.casefold() for model in models), 0)
    for line in text.splitlines():
        words = line.split()
        if len(words) >= 6 and words[0][0].lower() in ("m", "x") and words[5].casefold() in model_counts:
            model_counts[words[5].casefold()] += 1
    resistors = len(re.findall(r"^\s*R\S+\s+\S+\s+\S+\s+\S+", text, re.I | re.M))
    capacitors = len(re.findall(r"^\s*C\S+\s+\S+\s+\S+\s+\S+", text, re.I | re.M))
    return RcxCounts(", ".join(models), sum(model_counts.values()), resistors, capacitors, all(model_counts.values()))


def summarize_rcx(spice: Path, model: str) -> tuple[str, str]:
    counts = _count_rcx(spice, (model,))
    return counts.status, counts.describe()


def run_mos_extraction(pdk_root: Path, point: GeneratedLayout, mode: str) -> ExtractionResult:
    layout = Path(point.layout_path)
    directory = layout.parent / mode / layout.stem
    try:
        if not point.layout_path or not layout.is_file():
            raise ValueError(f"GDS file unavailable: {point.layout_path or point.message}")
        data = json.loads(layout.with_suffix(".json").read_text(encoding="utf-8"))
        values = data["actual"]
        name = data.get("pcell")
        top = "VERIFY_TOP"
        if name == INVERTER_NAME:
            devices = data["devices"]
            models = tuple(device["type"] for device in devices)
            if models != INVERTER_MODELS:
                raise ValueError("Expected one NFET and one PFET in inverter metadata")
            prefix = "inverter"
        else:
            model = values["type"]
            if name not in MOS_PCELL_NAMES or not isinstance(model, str) or not re.fullmatch(
                rf"sky130_fd_pr__{name}_\w+", model,
            ):
                raise ValueError("Expected Sky130A MOS metadata with a matching SPICE model")
            models = (model,)
            prefix = "nmos" if name == "nfet" else "pmos"
        directory.mkdir(parents=True, exist_ok=True)
        if mode == "lvs":
            reference = (
                _inverter_reference(top, devices) if name == INVERTER_NAME
                else _reference_spice(top, models[0], values)
            )
            (directory / f"{prefix}_reference.spice").write_text(reference, encoding="utf-8")
            spice = directory / f"{prefix}_extracted.spice"
        else:
            spice = directory / f"{prefix}_rcx.spice"

        error = run_sky130_magic(
            pdk_root, layout, top, f"extract_nmos_{mode}.tcl", spice, directory / "magic.log",
        )
        if error:
            return ExtractionResult(point.index, "ERROR", error, error.splitlines()[0])
        if mode == "lvs":
            setup = pdk_root / "libs.tech/netgen/sky130A_setup.tcl"
            status, details = _compare_lvs(directory, setup, top, prefix)
            if status == "PASS":
                summary = "Circuits match uniquely"
            elif status == "ERROR":
                summary = details.splitlines()[0]
            elif re.search(r"property errors", details, re.I):
                summary = "Device property differences"
            else:
                summary = "Netlist mismatch"
            return ExtractionResult(point.index, status, f"Files: {directory}\n\n{details}", summary)

        counts = _count_rcx(spice, models)
        return ExtractionResult(
            point.index, counts.status, f"Files: {directory}\n\n{counts.describe()}",
            "Expected MOS models found" if counts.all_models_present else "Expected MOS model missing",
            counts,
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        return ExtractionResult(point.index, "ERROR", str(error), str(error))


# Preserve the original entry point for standalone callers.
run_nmos_extraction = run_mos_extraction
