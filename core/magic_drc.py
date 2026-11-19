"""Run Sky130A Magic in a scratch directory against existing GDS."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def run_sky130_magic(
    pdk_root: Path, layout: Path, top_cell: str, script_name: str, output: Path, log: Path,
) -> str | None:
    executable = shutil.which("magic")
    if not executable:
        return "Magic executable not found"

    project = Path(__file__).resolve().parents[1]
    tech_dir = pdk_root / "libs.tech" / "magic"
    rcfile = tech_dir / "sky130A.magicrc"
    if not rcfile.is_file():
        rcfile = project / "config" / "sky130A.magicrc"
    if not (tech_dir / "sky130A.tech").is_file():
        return f"Sky130A Magic technology file not found: {tech_dir / 'sky130A.tech'}"

    script = project / "scripts" / script_name
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="pcell-magic-", dir=output.parent) as scratch_dir:
        scratch = Path(scratch_dir)
        output_tmp = scratch / output.name
        pdk_parent = pdk_root.parent
        if pdk_root.name != "sky130A":
            # The stock rcfile expects PDK_ROOT/sky130A even for renamed installs.
            (scratch / "sky130A").symlink_to(pdk_root, target_is_directory=True)
            pdk_parent = scratch
        env = os.environ.copy()
        env.update({
            "PDK_ROOT": str(pdk_parent),
            "PCELL_MAGIC_GDS": str(layout),
            "PCELL_MAGIC_TOP": top_cell,
            "PCELL_MAGIC_OUTPUT": str(output_tmp),
        })
        try:
            completed = subprocess.run(
                [executable, "-dnull", "-noconsole", "-rcfile", str(rcfile), str(script)],
                cwd=scratch, env=env, capture_output=True, text=True, errors="replace", timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return f"Magic could not complete: {error}"

        log.write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
        if completed.returncode or not output_tmp.is_file() or not output_tmp.stat().st_size:
            details = (completed.stderr or completed.stdout).strip()[-800:]
            return f"Magic did not complete (log: {log})\n{details}"
        output_tmp.replace(output)
    return None


def check_sky130_layout(pdk_root: Path, layout: Path, top_cell: str = "VERIFY_TOP") -> tuple[bool, str]:
    report = layout.with_name(f"{layout.stem}_drc.txt")
    log = layout.with_name(f"{layout.stem}_magic.log")
    error = run_sky130_magic(pdk_root, layout, top_cell, "run_nmos_drc.tcl", report, log)
    if error:
        return False, error
    match = re.match(r"DRC_TOTAL_ERRORS=(\d+)\n", report.read_text(encoding="utf-8"))
    if not match:
        return False, f"Magic returned an invalid DRC report (log: {log})"
    errors = int(match[1])
    return (
        errors == 0,
        f"Magic DRC found {errors} error tile(s) · {report}" if errors
        else f"Magic DRC passed · {report}",
    )
