"""Run Sky130A Magic DRC against an existing GDS artifact."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def check_sky130_layout(pdk_root: Path, layout: Path, top_cell: str = "VERIFY_TOP") -> tuple[bool, str]:
    executable = shutil.which("magic")
    if not executable:
        return False, "Magic executable not found"

    project = Path(__file__).resolve().parents[1]
    tech_dir = pdk_root / "libs.tech" / "magic"
    rcfile = tech_dir / "sky130A.magicrc"
    if not rcfile.is_file():
        rcfile = project / "config" / "sky130A.magicrc"
    if not (tech_dir / "sky130A.tech").is_file():
        return False, f"Sky130A Magic technology file not found: {tech_dir / 'sky130A.tech'}"

    report = layout.with_name(f"{layout.stem}_drc.txt")
    log = layout.with_name(f"{layout.stem}_magic.log")
    script = project / "scripts" / "run_nmos_drc.tcl"
    with TemporaryDirectory(prefix="pcell-magic-", dir=layout.parent) as scratch_dir:
        scratch = Path(scratch_dir)
        report_tmp = scratch / report.name
        pdk_parent = pdk_root.parent
        if pdk_root.name != "sky130A":
            # The stock rcfile expects PDK_ROOT/sky130A even for renamed installs.
            (scratch / "sky130A").symlink_to(pdk_root, target_is_directory=True)
            pdk_parent = scratch
        env = os.environ.copy()
        env.update({
            "PDK_ROOT": str(pdk_parent),
            "PCELL_DRC_GDS": str(layout),
            "PCELL_DRC_TOP": top_cell,
            "PCELL_DRC_REPORT": str(report_tmp),
        })
        try:
            completed = subprocess.run(
                [executable, "-dnull", "-noconsole", "-rcfile", str(rcfile), str(script)],
                cwd=scratch, env=env, capture_output=True, text=True, errors="replace", timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"Magic DRC could not complete: {error}"

        log.write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
        if completed.returncode or not report_tmp.is_file():
            details = (completed.stderr or completed.stdout).strip()[-800:]
            return False, f"Magic DRC did not complete (log: {log})\n{details}"
        summary = report_tmp.read_text(encoding="utf-8")
        match = re.match(r"DRC_TOTAL_ERRORS=(\d+)\n", summary)
        if not match:
            return False, f"Magic returned an invalid DRC report (log: {log})"
        report_tmp.replace(report)

    errors = int(match[1])
    return (
        errors == 0,
        f"Magic DRC found {errors} error tile(s) · {report}" if errors
        else f"Magic DRC passed · {report}",
    )
