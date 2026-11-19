import subprocess
from pathlib import Path
from unittest.mock import patch

from core.nmos_extraction import _compare_lvs, summarize_rcx


def test_netgen_property_error_overrides_connectivity_match(tmp_path: Path):
    setup = tmp_path / "sky130A_setup.tcl"
    setup.touch()
    for name in ("nmos_extracted.spice", "nmos_reference.spice"):
        (tmp_path / name).touch()

    def compare(command, *, cwd, **kwargs):
        assert command[3:5] == ["nmos_extracted.spice VERIFY_TOP", "nmos_reference.spice VERIFY_TOP"]
        (cwd / "nmos_lvs.log").write_text(
            "Circuits match uniquely.\nProperty errors were found.\n", encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    with patch("core.nmos_extraction.shutil.which", return_value="/usr/bin/netgen-lvs"), patch(
        "core.nmos_extraction.subprocess.run", side_effect=compare
    ):
        status, details = _compare_lvs(tmp_path, setup, "VERIFY_TOP")

    assert status == "FAIL"
    assert "Property errors were found." in details


def test_rcx_counts_instances_and_allows_zero_resistors(tmp_path: Path):
    spice = tmp_path / "nmos_rcx.spice"
    spice.write_text(
        "* sky130_fd_pr__nfet_01v8\n"
        "X0 D G S B sky130_fd_pr__nfet_01v8 w=0.42 l=0.15\n"
        "C0 D B 0.05628f\n",
        encoding="utf-8",
    )

    status, details = summarize_rcx(spice, "sky130_fd_pr__nfet_01v8")

    assert status == "PASS_BASIC"
    assert "MOS instances: 1" in details
    assert "Resistors: 0" in details
    assert "Capacitors: 1" in details
    assert summarize_rcx(spice, "sky130_fd_pr__nfet_01v8_lvt")[0] == "FAIL"
