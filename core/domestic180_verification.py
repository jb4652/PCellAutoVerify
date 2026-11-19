"""Geometry-derived verification for the domestic180 layer stack."""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from klayout import db as kdb

from pdks.domestic180.pcells import CONTACT, GATE, METAL, N_ACTIVE, N_BODY, PIN, P_ACTIVE, P_BODY

from .models import GeneratedLayout
from .nmos_extraction import ExtractionResult, RcxCounts


def is_domestic180(root: Path) -> bool:
    try:
        data = json.loads((root / "pdk.json").read_text(encoding="utf-8"))
        return isinstance(data, dict) and data.get("format") == "pcell-auto-verify-domestic180-v1"
    except (ValueError, OSError):
        return False


@dataclass(frozen=True)
class Device:
    model: str
    pins: tuple[str, str, str, str]  # D, G, S, B
    width: float
    length: float


class ConnectivityError(ValueError):
    """The GDS does not contain an extractable, connected domestic180 circuit."""


class Domestic180Layout:
    def __init__(self, path: Path):
        self.layout = kdb.Layout()
        self.layout.read(str(path))
        self.top = self.layout.cell("VERIFY_TOP")
        if self.top is None:
            raise ValueError("VERIFY_TOP is missing from the GDS")
        self.dbu = self.layout.dbu

    def region(self, layer):
        index = self.layout.find_layer(*layer)
        if index is None:
            return kdb.Region()
        return kdb.Region(self.top.begin_shapes_rec(index)).merged()

    def pins(self):
        index = self.layout.find_layer(*PIN)
        if index is None:
            return
        shapes = self.top.begin_shapes_rec(index)
        while not shapes.at_end():
            shape = shapes.shape()
            if shape.is_text():
                label = shape.text
                yield label.string, shapes.trans() * kdb.Point(label.x, label.y)
            shapes.next()


def check_drc(root: Path, path: Path) -> tuple[bool, str]:
    try:
        rules = json.loads((root / "pdk.json").read_text(encoding="utf-8"))
        geometry = Domestic180Layout(path)
        metal = geometry.region(METAL)
        active = geometry.region(N_ACTIVE) + geometry.region(P_ACTIVE)
        channel = active & geometry.region(GATE)
        dbu = geometry.dbu
        checks = {
            "gate minimum length": channel.width_check(round(rules["min_gate_um"] / dbu)).size(),
            "active minimum width": active.width_check(round(rules["min_active_width_um"] / dbu)).size(),
            "Metal1 minimum width": metal.width_check(round(rules["min_metal_width_um"] / dbu)).size(),
            "Metal1 minimum spacing": metal.space_check(round(rules["min_metal_spacing_um"] / dbu)).size(),
            "Metal1 minimum area": sum(
                poly.area() * dbu ** 2 < rules["min_metal_area_um2"] for poly in metal.each()
            ),
            "missing MOS channel": int(channel.is_empty()),
            "missing Metal1": int(metal.is_empty()),
        }
        failures = [f"{name}: {count}" for name, count in checks.items() if count]
        summary = "; ".join(failures) if failures else "All domestic180 geometry checks passed"
        report = path.with_name(f"{path.stem}_drc.txt")
        report.write_text(summary + "\n", encoding="utf-8")
        return not failures, f"{summary} · {report}"
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        return False, f"domestic180 DRC could not complete: {error}"


def _extract(geometry: Domestic180Layout) -> tuple[list[Device], dict]:
    conductors = list(geometry.region(METAL).each())
    names = {}
    areas = {}
    for name, point in geometry.pins():
        matches = [index for index, poly in enumerate(conductors) if poly.inside(point)]
        if len(matches) != 1 or matches[0] in names or name in areas:
            raise ConnectivityError(f"Missing, duplicate or shorted terminal: {name}")
        index = matches[0]
        names[index] = name
        poly = conductors[index]
        areas[name] = (poly.area() * geometry.dbu ** 2, poly.perimeter() * geometry.dbu)

    contacts = geometry.region(CONTACT)
    gate = geometry.region(GATE)
    devices = []

    def net(terminal):
        contact = terminal & contacts
        matches = [
            index for index, conductor in enumerate(conductors)
            if not (kdb.Region(conductor) & contact).is_empty()
        ]
        if len(matches) != 1 or matches[0] not in names:
            raise ConnectivityError("A MOS terminal is open, shorted or lacks a named net")
        return names[matches[0]]

    for model, active_layer, body_layer in (
        ("domestic180_nmos", N_ACTIVE, N_BODY), ("domestic180_pmos", P_ACTIVE, P_BODY),
    ):
        active = geometry.region(active_layer)
        if active.is_empty():
            continue
        channels = list((active & gate).each())
        diffusions = sorted((active - gate).each(), key=lambda poly: poly.bbox().left)
        if len(channels) != 1 or len(diffusions) != 2:
            raise ConnectivityError(f"Expected one single-finger device for {model}")
        channel = channels[0].bbox()
        gate_shapes = kdb.Region()
        for poly in gate.each():
            if not (kdb.Region(poly) & kdb.Region(channel)).is_empty():
                gate_shapes.insert(poly)
        source, drain = (net(kdb.Region(poly)) for poly in diffusions)
        pins = (drain, net(gate_shapes), source, net(geometry.region(body_layer)))
        devices.append(Device(model, pins, round(channel.height() * geometry.dbu, 6),
                              round(channel.width() * geometry.dbu, 6)))
    if not devices:
        raise ConnectivityError("No MOS device was extracted")
    return devices, areas


def _reference(name: str, parameters: dict[str, str]) -> list[Device]:
    parameters = {key: round(float(value), 6) for key, value in parameters.items()}
    if name == "inverter":
        return [
            Device("domestic180_nmos", ("Y", "A", "VSS", "VSS"), parameters.get("wn", .60), parameters.get("ln", .18)),
            Device("domestic180_pmos", ("Y", "A", "VDD", "VDD"), parameters.get("wp", .60), parameters.get("lp", .18)),
        ]
    if name not in ("nmos", "pmos"):
        raise ValueError(f"Unknown domestic180 PCell: {name}")
    return [Device(f"domestic180_{name}", ("D", "G", "S", "B"), parameters.get("w", .60), parameters.get("l", .18))]


def _spice(devices: list[Device], ports: Iterable[str], parasitics: Sequence[str] = ()) -> str:
    lines = [f".subckt VERIFY_TOP {' '.join(sorted(ports))}"]
    for index, device in enumerate(devices, 1):
        lines.append(f"M{index} {' '.join(device.pins)} {device.model} W={device.width:g}u L={device.length:g}u")
    return "\n".join([*lines, *parasitics, ".ends VERIFY_TOP", ""])


def run_extraction(root: Path, point: GeneratedLayout, mode: str) -> ExtractionResult:
    try:
        if not point.layout_path:
            raise ValueError(point.message)
        path = Path(point.layout_path)
        devices, nets = _extract(Domestic180Layout(path))
        reference = _reference(path.stem.rsplit("_", 1)[0], point.parameters)
        ports = {pin for device in reference for pin in device.pins}
        directory = path.parent / mode / path.stem
        directory.mkdir(parents=True, exist_ok=True)
        if mode == "lvs":
            (directory / "reference.spice").write_text(_spice(reference, ports), encoding="utf-8")
            (directory / "extracted.spice").write_text(_spice(devices, nets), encoding="utf-8")
            passed = set(nets) == ports and devices == reference
            summary = "Geometry, ports and connectivity match" if passed else "Extracted circuit differs from reference"
            details = f"{summary}\n\nExtracted:\n{_spice(devices, nets)}\nReference:\n{_spice(reference, ports)}"
            (directory / "lvs.txt").write_text(details, encoding="utf-8")
            return ExtractionResult(point.index, "PASS" if passed else "FAIL", f"{details}\nFiles: {directory}", summary)

        rules = json.loads((root / "pdk.json").read_text(encoding="utf-8"))
        # Lumped estimates: one pin lead resistor and one area capacitance per named net.
        extracted_nets = {net: f"internal_{index}" for index, net in enumerate(sorted(nets), 1)}
        parasitics = []
        for index, net in enumerate(sorted(nets), 1):
            area, perimeter = nets[net]
            squares = perimeter ** 2 / (16 * area)
            internal = extracted_nets[net]
            parasitics.append(f"R{index} {net} {internal} {squares * rules['metal_ohms_per_square']:.6g}")
            parasitics.append(f"C{index} {internal} 0 {area * rules['metal_ff_per_um2']:.6g}f")
        routed = [Device(d.model, tuple(extracted_nets[pin] for pin in d.pins), d.width, d.length) for d in devices]
        (directory / "estimated_rcx.spice").write_text(_spice(routed, nets, parasitics), encoding="utf-8")
        extracted_models = {device.model for device in devices}
        expected_models = {device.model for device in reference}
        counts = RcxCounts(
            ", ".join(sorted(extracted_models)), len(devices), len(nets), len(nets),
            expected_models.issubset(extracted_models),
        )
        summary = "Geometry-based lumped RC estimates"
        details = f"{summary} from Metal1 area and perimeter.\n{counts.describe()}\nFiles: {directory}"
        return ExtractionResult(point.index, counts.status, details, summary, counts)
    except ConnectivityError as error:
        return ExtractionResult(point.index, "FAIL" if mode == "lvs" else "ERROR", str(error), str(error))
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        return ExtractionResult(point.index, "ERROR", str(error), str(error))
