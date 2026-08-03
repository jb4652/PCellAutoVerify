"""KLayout-backed PCell generation and DRC execution."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .models import PCell, VerificationResult


_RUNNER = r'''import importlib, json, os, runpy, sys, pya
source = os.environ["PCELL_VERIFY_SOURCE"]
class_name = os.environ["PCELL_VERIFY_CLASS"]
parameters = os.environ["PCELL_VERIFY_PARAMETERS"]
output = os.environ["PCELL_VERIFY_OUTPUT"]
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
        if not decks:
            decks = sorted(self.pdk_root.rglob("*drc*.drc"))
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
        """Expose the application's installed packages to KLayout's Python."""
        environment = os.environ.copy()
        paths = [path for path in sys.path if path]
        paths.extend(
            path
            for path in environment.get("PYTHONPATH", "").split(os.pathsep)
            if path
        )
        # KLayout embeds a separate Python interpreter, so an activated virtual
        # environment's site-packages is not necessarily on its import path.
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
            environment = self._environment()
            environment.update({
                "PCELL_VERIFY_SOURCE": str(source),
                "PCELL_VERIFY_CLASS": pcell.name,
                "PCELL_VERIFY_PARAMETERS": json.dumps(self._values(point)),
                "PCELL_VERIFY_OUTPUT": str(layout),
            })
            generated = subprocess.run(
                [executable, "-b", "-r", str(runner)],
                capture_output=True, text=True, timeout=120, env=environment,
            )
            if generated.returncode or not layout.exists():
                message = (generated.stderr or generated.stdout or "PCell generation failed").strip()
                results.append(VerificationResult(index, point, False, message[-1000:]))
                continue
            if deck is None:
                results.append(VerificationResult(index, point, False, "No KLayout DRC deck (*.lydrc) found", str(layout)))
                continue
            report = self.output_root / f"{pcell.name}_{index:04d}.lyrdb"
            checked = subprocess.run(
                [executable, "-b", "-r", str(deck), "-rd", f"input={layout}",
                 "-rd", f"report={report}"], capture_output=True, text=True, timeout=300,
                cwd=self.pdk_root, env=environment,
            )
            violations = report.read_text(encoding="utf-8", errors="ignore").count("<item>") if report.exists() else 0
            passed = checked.returncode == 0 and report.exists() and violations == 0
            message = "DRC passed" if passed else (
                f"DRC found {violations} violation(s)" if report.exists() else
                (checked.stderr or checked.stdout or "DRC did not create a report").strip()[-1000:]
            )
            results.append(VerificationResult(index, point, passed, message, str(layout)))
        return results
