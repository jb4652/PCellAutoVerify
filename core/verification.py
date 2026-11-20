"""KLayout-backed PCell generation and DRC execution."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .process_console import run_process
from .domestic180_verification import check_drc as check_domestic180_drc, is_domestic180
from .magic_drc import check_sky130_layout
from .models import GeneratedLayout, PCell, VerificationResult
from .sky130_nmos import MOS_PCELL_NAMES
from .sky130_library import (
    SKY130_PYTHON_PATH,
    find_sky130_python_dir,
    is_sky130a,
    sky130_pdk_root,
)


_RUNNER = r'''import importlib, json, os, re, runpy, sys
try:
    import pya
except ModuleNotFoundError:
    # The PyPI KLayout package exposes its API as ``klayout.db`` rather than
    # ``pya``.  Register the traditional name too, since PDK PCells commonly
    # import it directly.
    import klayout.db as pya
    sys.modules["pya"] = pya
# PYTHONPATH is inherited from the GUI process so that PCells can import their
# dependencies. KLayout can, however, embed a different Python minor version.
# Never let (for example) python3.11/site-packages shadow KLayout's native
# python3.12 packages: extension modules such as NumPy cannot be loaded by the
# other interpreter.
def compatible_path(path):
    versions = re.findall(r"(?:^|[/\\])python(\d+)\.(\d+)(?:[/\\]|$)", path)
    return all((int(major), int(minor)) == sys.version_info[:2]
               for major, minor in versions)
sys.path[:] = [path for path in sys.path if compatible_path(path)]
source = os.environ["PCELL_VERIFY_SOURCE"]
class_name = os.environ["PCELL_VERIFY_CLASS"]
parameters = os.environ["PCELL_VERIFY_PARAMETERS"]
output = os.environ["PCELL_VERIFY_OUTPUT"]
preview = os.environ.get("PCELL_VERIFY_PREVIEW", "")
source_path = os.path.abspath(source)
layout = pya.Layout()
values = json.loads(parameters)
metal1_test_width = values.pop("metal1_test_width", None)
library_path = os.environ.get("PCELL_VERIFY_LIBRARY")
def load_source_declaration(source_path, class_name):
    package_parts = []
    package_dir = os.path.dirname(source_path)
    while os.path.isfile(os.path.join(package_dir, "__init__.py")):
        package_parts.insert(0, os.path.basename(package_dir))
        package_dir = os.path.dirname(package_dir)
    if package_parts:
        sys.path.insert(0, package_dir)
        source_module = os.path.splitext(os.path.basename(source_path))[0]
        module_name = ".".join(package_parts + ([] if source_module == "__init__" else [source_module]))
        namespace = vars(importlib.import_module(module_name))
    else:
        namespace = runpy.run_path(source_path)
    cls = namespace.get(class_name)
    if cls is None:
        raise RuntimeError("PCell class not found: " + class_name)
    return cls()

changed = os.environ.get("PCELL_VERIFY_CALLBACK")
if changed:
    from pathlib import Path
    from core.parameter_callback import evaluate_callback, evaluate_inverter_callback
    from core.sky130_inverter import INVERTER_NAME

    print(f"[parameter edit] {class_name}.{changed} = {values.get(changed)!r}", flush=True)
    if library_path and class_name == INVERTER_NAME:
        result = evaluate_inverter_callback(values)
    else:
        if library_path:
            from core.sky130_library import load_library
            library = load_library(Path(library_path))
            declaration = library.layout().pcell_declaration(class_name)
        else:
            declaration = load_source_declaration(source_path, class_name)
        if declaration is None or not hasattr(declaration, "coerce_parameters"):
            raise ValueError(f"No parameter declaration available for {class_name}")
        result = evaluate_callback(layout, declaration, changed, values)
    Path(output).write_text(json.dumps(result), encoding="utf-8")
    sys.exit(0)

metadata = None
if library_path:
    from pathlib import Path
    from core.sky130_library import load_library

    from core.sky130_inverter import INVERTER_NAME, instantiate_inverter
    from core.sky130_nmos import MOS_PCELL_NAMES, instantiate_mos, write_metadata

    if class_name == INVERTER_NAME:
        cell, metadata = instantiate_inverter(layout, Path(library_path), values)
    elif class_name in MOS_PCELL_NAMES:
        cell, metadata = instantiate_mos(layout, Path(library_path), class_name, values)
    else:
        library = load_library(Path(library_path))
        cell = layout.create_cell(class_name, library.name(), values)
else:
    declaration = load_source_declaration(source_path, class_name)
    layout.register_pcell(class_name, declaration)
    cell = layout.create_cell(class_name, values)
if cell is None:
    raise RuntimeError("KLayout could not instantiate the PCell")
# KLayout deliberately catches exceptions raised by ``produce_impl``.  Rather
# than propagating them to Python, it puts the traceback on its special error
# layer as text.  Without checking that layer we would write an error message
# as a GDS layout and an empty layout could then (misleadingly) pass DRC.
error_messages = []
if hasattr(layout, "error_layer") and hasattr(layout, "each_cell"):
    error_layer = layout.error_layer()
    for generated_cell in layout.each_cell():
        for shape in generated_cell.shapes(error_layer).each():
            if shape.is_text():
                error_messages.append(shape.text.string)
            else:
                error_messages.append("unknown PCell generation error")
if error_messages:
    raise RuntimeError("PCell generation failed: " + "\n".join(error_messages))
top = cell if getattr(cell, "name", "") == "VERIFY_TOP" else layout.create_cell("VERIFY_TOP")
if top != cell:
    top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans()))
if metal1_test_width is not None:
    from core.sky130_inverter import SKY130_REGRESSION_CELLS

    if not library_path or class_name not in SKY130_REGRESSION_CELLS:
        raise ValueError("The Metal1 DRC test is only defined for the Sky130A regression cells")
    if metal1_test_width != 0.035:
        raise ValueError("The Metal1 DRC test width must be 0.035 µm")
    # Isolate the shape from the electrical circuit and keep it on the 5 nm grid.
    x = ((top.bbox().right + 4) // 5) * 5 + 2000
    width = round(metal1_test_width / layout.dbu)
    height = round(0.5 / layout.dbu)
    top.shapes(layout.layer(68, 20)).insert(pya.Box(x, 0, x + width, height))
    metadata["metal1_test_width"] = metal1_test_width
layout.write(output)
if metadata is not None:
    write_metadata(Path(output), metadata)
if preview:
    try:
        from klayout.lay import LayoutView

        view = LayoutView()
        view.show_layout(layout, True)
        view.max_hier()
        view.zoom_fit()
        view.save_image(preview, 1600, 1200)
    except Exception as error:
        # A preview is a convenience and must never turn a successfully
        # generated layout into a failed verification result.
        sys.stderr.write("Unable to create layout preview: " + str(error) + "\n")
'''


class KLayoutVerifier:
    """Generate GDS with KLayout and check it with the PDK’s DRC engine."""

    def __init__(self, pdk_root: str, output_root: str | None = None):
        self.pdk_root = sky130_pdk_root(Path(pdk_root).expanduser().absolute()).resolve()
        if output_root:
            self.output_root = Path(output_root).expanduser().resolve()
        else:
            project = Path(__file__).resolve().parents[1]
            base = (project if (project / "pyproject.toml").is_file() else Path.cwd()) / "output/verification"
            base.mkdir(parents=True, exist_ok=True)
            self.output_root = Path(tempfile.mkdtemp(prefix="run-", dir=base))

    def _deck(self) -> Path | None:
        decks = sorted(self.pdk_root.rglob("*.lydrc"))
        # GF180's .lydrc is a GUI launcher for run_drc.py.  Running that
        # launcher inside KLayout requires ``docopt`` to be installed for
        # KLayout's embedded (and potentially different) Python interpreter.
        # Execute the standalone rule deck directly instead; this is also the
        # same deck eventually selected by the launcher.
        standalone = sorted(self.pdk_root.rglob("*.drc"))
        if decks and standalone and any(self.pdk_root.rglob("run_drc.py")):
            return min(standalone, key=lambda path: (len(path.parts), str(path)))
        if not decks:
            decks = standalone
        return decks[0] if decks else None

    @staticmethod
    def _values(point: dict[str, str]) -> dict[str, object]:
        values: dict[str, object] = {}
        for key, value in point.items():
            try:
                values[key] = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                values[key] = value
        return values

    @staticmethod
    def _environment() -> dict[str, str]:
        """Expose installed packages without replacing KLayout's standard library.

        KLayout may embed a different Python patch or minor version from the
        application.  Adding the application's standard-library directory to
        ``PYTHONPATH`` can then make Python modules such as :mod:`re` disagree
        with KLayout's built-in extension modules (reported as an ``SRE module
        mismatch``).  Project and site-package paths are useful to PCells, but
        the host interpreter's standard-library paths must be left out.
        """
        environment = os.environ.copy()
        paths = [str(Path(__file__).resolve().parents[1]), *[path for path in sys.path if path]]
        paths.extend(
            path
            for path in environment.get("PYTHONPATH", "").split(os.pathsep)
            if path
        )
        standard_library = {
            Path(path).resolve()
            for key in ("stdlib", "platstdlib")
            if (path := sysconfig.get_path(key))
        }

        def safe_for_embedded_python(path: str) -> bool:
            resolved = Path(path).resolve()
            # site-packages commonly lives below the stdlib directory, but it
            # contains third-party dependencies rather than interpreter files.
            if any(part in {"site-packages", "dist-packages"} for part in resolved.parts):
                return True
            return not any(
                resolved == root or root in resolved.parents
                for root in standard_library
            )

        paths = [os.path.abspath(path) for path in paths if safe_for_embedded_python(path)]
        # KLayout embeds a separate Python interpreter, so an activated virtual
        # environment's site-packages is not necessarily on its import path.
        # The runner removes paths belonging to a different Python minor after
        # it starts inside KLayout; that decision cannot be made in this host
        # process because the two programs may use different interpreters.
        environment["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(paths))
        return environment

    @staticmethod
    def _violation_count(report: Path) -> int | None:
        """Count result-database items without depending on XML formatting."""
        try:
            root = ET.parse(report).getroot()
        except (ET.ParseError, OSError):
            return None
        return sum(
            1 for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] == "item"
        )

    def _library_path(self, pcell: PCell) -> Path | None:
        source = self.pdk_root / pcell.source
        # Historical imports sometimes stored only the source file or the library
        # directory. A MOS PCell from that tree still needs the compatibility code.
        library_path = source if (source / "cells" / "__init__.py").is_file() else None
        legacy_sky130 = pcell.name in MOS_PCELL_NAMES and (
            is_sky130a(self.pdk_root.name)
            or source.is_relative_to(self.pdk_root / SKY130_PYTHON_PATH)
        )
        if pcell.library_path or legacy_sky130:
            saved_path = self.pdk_root / pcell.library_path
            library_path = (
                find_sky130_python_dir(saved_path)
                or library_path
                or find_sky130_python_dir(self.pdk_root)
            )
            if library_path is None:
                raise ValueError(f"Sky130A cells/__init__.py not found under {saved_path} or {self.pdk_root}")
        return library_path

    @classmethod
    def evaluate_parameter_edit(
        cls, pdk_root: str, pcell: PCell, changed: str, point: dict[str, str],
    ) -> dict | None:
        with tempfile.TemporaryDirectory(prefix="pcell-callback-") as directory:
            verifier = cls(pdk_root, directory)
            source = verifier.pdk_root / pcell.source
            library_path = verifier._library_path(pcell)
            if not library_path and not source.is_file():
                return None
            output = Path(directory) / "callback.json"
            runner = Path(directory) / "callback.py"
            runner.write_text(_RUNNER, encoding="utf-8")
            environment = verifier._environment()
            environment.update({
                "PCELL_VERIFY_SOURCE": str(source),
                "PCELL_VERIFY_LIBRARY": str(library_path) if library_path else "",
                "PCELL_VERIFY_CLASS": pcell.name,
                "PCELL_VERIFY_PARAMETERS": json.dumps(verifier._values(point)),
                "PCELL_VERIFY_OUTPUT": str(output),
                "PCELL_VERIFY_CALLBACK": changed,
            })
            result = run_process(
                [sys.executable, str(runner)], capture_output=True, text=True,
                errors="replace", timeout=30, env=environment,
            )
            if result.returncode or not output.is_file():
                details = result.stderr.strip() or result.stdout.strip()
                raise ValueError(details.splitlines()[-1] if details else "PCell callback did not return a result")
            return json.loads(output.read_text(encoding="utf-8"))

    def generate_layouts(self, pcell: PCell, points: list[dict[str, str]]) -> list[GeneratedLayout]:
        source = self.pdk_root / pcell.source
        try:
            library_path = self._library_path(pcell)
        except ValueError as error:
            return [GeneratedLayout(index, point, str(error)) for index, point in enumerate(points, 1)]
        self.output_root.mkdir(parents=True, exist_ok=True)
        runner = self.output_root / "instantiate.py"
        runner.write_text(_RUNNER, encoding="utf-8")
        results: list[GeneratedLayout] = []
        for index, point in enumerate(points, 1):
            layout = self.output_root / f"{pcell.name}_{index:04d}.gds"
            preview = self.output_root / f"{pcell.name}_{index:04d}.png"
            environment = self._environment()
            environment.pop("PCELL_VERIFY_CALLBACK", None)
            environment.update({
                "PCELL_VERIFY_SOURCE": str(source),
                "PCELL_VERIFY_LIBRARY": str(library_path) if library_path else "",
                "PCELL_VERIFY_CLASS": pcell.name,
                "PCELL_VERIFY_PARAMETERS": json.dumps(self._values(point)),
                "PCELL_VERIFY_OUTPUT": str(layout),
                "PCELL_VERIFY_PREVIEW": str(preview),
            })
            # Instantiate with the application's interpreter.  KLayout's
            # embedded Python can have a different minor version and therefore
            # cannot load binary dependencies (notably NumPy) installed for
            # the application.  The ``klayout`` Python package provides the
            # same layout API without crossing that interpreter boundary.
            try:
                generated = run_process(
                    [sys.executable, str(runner)],
                    capture_output=True, text=True, timeout=120, env=environment,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                results.append(GeneratedLayout(index, point, f"GDS generation failed: {error}"))
                continue
            if generated.returncode or not layout.exists():
                message = (generated.stderr or generated.stdout or "PCell generation failed").strip()
                results.append(GeneratedLayout(index, point, message[-1000:]))
                continue
            results.append(GeneratedLayout(
                index, point, "GDS generated", str(layout), str(preview) if preview.exists() else "",
            ))
        return results

    def check_layouts(self, layouts: list[GeneratedLayout]) -> list[VerificationResult]:
        """Check the existing artifacts without invoking the PCell generator."""
        use_domestic180 = is_domestic180(self.pdk_root)
        use_magic = is_sky130a(self.pdk_root.name) or (
            self.pdk_root / "libs.tech/magic/sky130A.tech"
        ).is_file()
        deck = None if use_magic or use_domestic180 else self._deck()
        executable = None if use_magic or use_domestic180 else shutil.which("klayout")
        results = []
        for generated in layouts:
            passed = False
            layout = Path(generated.layout_path)
            if not generated.layout_path:
                message = generated.message
            elif not layout.is_file():
                message = f"GDS file not found: {layout}"
            elif use_domestic180:
                passed, message = check_domestic180_drc(self.pdk_root, layout)
            elif use_magic:
                passed, message = check_sky130_layout(self.pdk_root, layout)
            elif not executable:
                message = "KLayout executable not found"
            elif deck is None:
                message = "No KLayout DRC deck (*.lydrc or *.drc) found"
            else:
                passed, message = self._check_klayout(executable, deck, layout)
            results.append(VerificationResult(
                generated.index, generated.parameters, passed, message,
                generated.layout_path if layout.is_file() else "", generated.preview_path,
            ))
        return results

    def _check_klayout(self, executable: str, deck: Path, layout: Path) -> tuple[bool, str]:
        report = layout.with_suffix(".lyrdb")
        report.unlink(missing_ok=True)
        # Different decks use different variables for the top cell.
        runtime_data = (
            ("input", layout),
            ("report", report),
            ("topcell", "VERIFY_TOP"),
            ("cell_name", "VERIFY_TOP"),
            ("cell", "VERIFY_TOP"),
        )
        arguments = [executable, "-b", "-r", str(deck)]
        for name, value in runtime_data:
            arguments.extend(("-rd", f"{name}={value}"))
        try:
            checked = run_process(
                arguments, capture_output=True, text=True, timeout=300,
                cwd=self.pdk_root, env=self._environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"DRC could not complete: {error}"
        violations = self._violation_count(report)
        if checked.returncode or violations is None:
            message = checked.stderr or checked.stdout or "DRC did not create a valid report"
            return False, message.strip()[-1000:]
        if violations:
            return False, f"DRC found {violations} violation(s)"
        return True, "DRC passed"

    def verify(self, pcell: PCell, points: list[dict[str, str]]) -> list[VerificationResult]:
        """Generate and check in one operation for existing non-GUI callers."""
        return self.check_layouts(self.generate_layouts(pcell, points))
