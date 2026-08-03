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
from pathlib import Path

from .models import PCell, VerificationResult


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
layout = pya.Layout()
declaration = cls()
layout.register_pcell(class_name, declaration)
values = json.loads(parameters)
cell = layout.create_cell(class_name, values)
if cell is None:
    raise RuntimeError("KLayout could not instantiate the PCell")
top = layout.create_cell("VERIFY_TOP")
top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans()))
layout.write(output)
if preview:
    try:
        view = pya.LayoutView()
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
    """Generate every layout and run the first DRC deck found in the PDK."""

    def __init__(self, pdk_root: str, output_root: str | None = None):
        self.pdk_root = Path(pdk_root)
        self.output_root = Path(output_root) if output_root else Path(
            tempfile.mkdtemp(prefix="pcell-verify-")
        )

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
        paths = [path for path in sys.path if path]
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

        paths = [path for path in paths if safe_for_embedded_python(path)]
        # KLayout embeds a separate Python interpreter, so an activated virtual
        # environment's site-packages is not necessarily on its import path.
        # The runner removes paths belonging to a different Python minor after
        # it starts inside KLayout; that decision cannot be made in this host
        # process because the two programs may use different interpreters.
        environment["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(paths))
        return environment

    def verify(self, pcell: PCell, points: list[dict[str, str]]) -> list[VerificationResult]:
        executable = shutil.which("klayout")
        if not executable:
            return [VerificationResult(i + 1, point, False, "KLayout executable not found") for i, point in enumerate(points)]
        source = self.pdk_root / pcell.source
        deck = self._deck()
        self.output_root.mkdir(parents=True, exist_ok=True)
        runner = self.output_root / "instantiate.py"
        runner.write_text(_RUNNER, encoding="utf-8")
        results: list[VerificationResult] = []
        for index, point in enumerate(points, 1):
            layout = self.output_root / f"{pcell.name}_{index:04d}.gds"
            preview = self.output_root / f"{pcell.name}_{index:04d}.png"
            environment = self._environment()
            environment.update({
                "PCELL_VERIFY_SOURCE": str(source),
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
            generated = subprocess.run(
                [sys.executable, str(runner)],
                capture_output=True, text=True, timeout=120, env=environment,
            )
            if generated.returncode or not layout.exists():
                message = (generated.stderr or generated.stdout or "PCell generation failed").strip()
                results.append(VerificationResult(index, point, False, message[-1000:]))
                continue
            if deck is None:
                results.append(VerificationResult(
                    index, point, False, "No KLayout DRC deck (*.lydrc or *.drc) found",
                    str(layout), str(preview) if preview.exists() else "",
                ))
                continue
            report = self.output_root / f"{pcell.name}_{index:04d}.lyrdb"
            # Rule decks do not agree on the runtime-data name used for the
            # selected cell.  In particular, GF180's component decks read
            # ``cell_name`` while other open-PDK decks use ``topcell`` or
            # ``cell``.  Supplying all three aliases is harmless to KLayout
            # and prevents source(input, "") from looking up an empty cell.
            runtime_data = (
                ("input", layout),
                ("report", report),
                ("topcell", "VERIFY_TOP"),
                ("cell_name", "VERIFY_TOP"),
                ("cell", "VERIFY_TOP"),
            )
            drc_arguments = [executable, "-b", "-r", str(deck)]
            for name, value in runtime_data:
                drc_arguments.extend(("-rd", f"{name}={value}"))
            checked = subprocess.run(
                drc_arguments,
                capture_output=True, text=True, timeout=300,
                cwd=self.pdk_root, env=environment,
            )
            violations = report.read_text(encoding="utf-8", errors="ignore").count("<item>") if report.exists() else 0
            passed = checked.returncode == 0 and report.exists() and violations == 0
            message = "DRC passed" if passed else (
                f"DRC found {violations} violation(s)" if report.exists() else
                (checked.stderr or checked.stdout or "DRC did not create a report").strip()[-1000:]
            )
            results.append(VerificationResult(
                index, point, passed, message, str(layout),
                str(preview) if preview.exists() else "",
            ))
        return results
