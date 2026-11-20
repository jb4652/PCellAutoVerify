import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from core.nmos_extraction import _compare_lvs, summarize_rcx


@pytest.mark.parametrize("prefix", ["nmos", "pmos"])
def test_netgen_property_error_overrides_connectivity_match(tmp_path: Path, prefix: str):
    setup = tmp_path / "sky130A_setup.tcl"
    setup.touch()
    for name in (f"{prefix}_extracted.spice", f"{prefix}_reference.spice"):
        (tmp_path / name).touch()

    def compare(command, *, cwd, **kwargs):
        assert command[3:5] == [f"{prefix}_extracted.spice VERIFY_TOP", f"{prefix}_reference.spice VERIFY_TOP"]
        (cwd / f"{prefix}_lvs.log").write_text(
            "Circuits match uniquely.\nProperty errors were found.\n", encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    with patch("core.nmos_extraction.shutil.which", return_value="/usr/bin/netgen-lvs"), patch(
        "core.nmos_extraction.subprocess.run", side_effect=compare
    ):
        status, details = _compare_lvs(tmp_path, setup, "VERIFY_TOP", prefix)

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
    assert "(top)/C0: D ↔ B = 0.05628f" in details
    assert summarize_rcx(spice, "sky130_fd_pr__nfet_01v8_lvt")[0] == "FAIL"


def test_inverter_reference_connects_both_body_terminals_to_supply():
    from core.nmos_extraction import _inverter_reference

    devices = [
        {"type": f"sky130_fd_pr__{name}_01v8", "w": 0.42, "l": 0.15, "nf": 1}
        for name in ("nfet", "pfet")
    ]
    reference = _inverter_reference("VERIFY_TOP", devices)
    assert ".subckt VERIFY_TOP A Y VDD VSS" in reference
    assert "Xnfet Y A VSS VSS sky130_fd_pr__nfet_01v8" in reference
    assert "Xpfet Y A VDD VDD sky130_fd_pr__pfet_01v8" in reference


def test_rcx_details_preserve_scope_nodes_and_spice_units(tmp_path: Path):
    spice = tmp_path / "rcx.spice"
    spice.write_text(
        ".subckt LEFT A Y\n"
        "R0 A Y 2.5k\n"
        "C0 Y 0\n+ 12f\n"
        ".ends LEFT\n"
        ".subckt RIGHT A Y\n"
        "C0 A Y 1e-15\n"
        ".ends RIGHT\n",
        encoding="utf-8",
    )
    _, details = summarize_rcx(spice, "domestic180_nmos")
    assert "LEFT/R0: A ↔ Y = 2.5k" in details
    assert "LEFT/C0: Y ↔ 0 = 12f" in details
    assert "RIGHT/C0: A ↔ Y = 1e-15" in details
