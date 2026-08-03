import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from unittest.mock import patch

from core import KLayoutVerifier, PCell
from core.verification import _RUNNER


def test_gf180_uses_standalone_deck_instead_of_python_launcher(tmp_path: Path):
    macro = tmp_path / "tech" / "macros" / "gf180mcu_drc.lydrc"
    launcher = tmp_path / "tech" / "drc" / "run_drc.py"
    deck = tmp_path / "tech" / "drc" / "gf180mcu.drc"
    component = tmp_path / "tech" / "drc" / "rule_decks" / "antenna.drc"
    for path in (macro, launcher, deck, component):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    assert KLayoutVerifier(str(tmp_path))._deck() == deck


def test_pcell_runner_uses_environment_instead_of_unsupported_separator(tmp_path: Path):
    pdk_root = tmp_path / "pdk"
    pdk_root.mkdir()
    (pdk_root / "device.py").write_text("class Device: pass\n", encoding="utf-8")
    (pdk_root / "checks.lydrc").write_text("# DRC deck\n", encoding="utf-8")
    output_root = tmp_path / "output"
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if Path(command[-1]).name == "instantiate.py":
            Path(kwargs["env"]["PCELL_VERIFY_OUTPUT"]).write_text("layout", encoding="utf-8")
        else:
            report_argument = command[command.index("-rd", command.index("-rd") + 1) + 1]
            Path(report_argument.removeprefix("report=")).write_text("<report/>", encoding="utf-8")
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with patch("core.verification.shutil.which", return_value="/usr/bin/klayout"), patch(
        "core.verification.subprocess.run", side_effect=run
    ):
        results = KLayoutVerifier(str(pdk_root), str(output_root)).verify(
            PCell("Device", "device.py"), [{"width": "1.5"}]
        )

    generation_command, generation_options = calls[0]
    assert generation_command == [sys.executable, str(output_root / "instantiate.py")]
    assert "--" not in generation_command
    assert generation_options["env"]["PCELL_VERIFY_CLASS"] == "Device"
    assert generation_options["env"]["PCELL_VERIFY_PARAMETERS"] == '{"width": 1.5}'
    assert generation_options["env"]["PCELL_VERIFY_PREVIEW"] == str(
        output_root / "Device_0001.png"
    )
    python_paths = generation_options["env"]["PYTHONPATH"].split(os.pathsep)
    assert str(Path(sysconfig.get_path("stdlib")).resolve()) not in python_paths
    assert any("site-packages" in path for path in python_paths)
    assert calls[1][1]["env"] is generation_options["env"]
    drc_command = calls[1][0]
    assert [
        drc_command[index + 1]
        for index, argument in enumerate(drc_command)
        if argument == "-rd"
    ] == [
        f"input={output_root / 'Device_0001.gds'}",
        f"report={output_root / 'Device_0001.lyrdb'}",
        "topcell=VERIFY_TOP",
        "cell_name=VERIFY_TOP",
        "cell=VERIFY_TOP",
    ]
    assert results[0].passed


def test_klayout_environment_preserves_existing_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(["/custom/packages", sys.path[0]]))

    paths = KLayoutVerifier._environment()["PYTHONPATH"].split(os.pathsep)

    assert "/custom/packages" in paths
    assert len(paths) == len(set(paths))


def test_klayout_environment_excludes_host_standard_library(monkeypatch, tmp_path):
    stdlib = tmp_path / "lib" / "python3.12"
    site_packages = stdlib / "site-packages"
    project = tmp_path / "project"
    monkeypatch.setattr(
        sys,
        "path",
        [str(stdlib), str(stdlib / "lib-dynload"), str(site_packages), str(project)],
    )
    monkeypatch.setattr(
        sysconfig,
        "get_path",
        lambda key: str(stdlib) if key in {"stdlib", "platstdlib"} else None,
    )

    paths = KLayoutVerifier._environment()["PYTHONPATH"].split(os.pathsep)

    assert str(stdlib) not in paths
    assert str(stdlib / "lib-dynload") not in paths
    assert str(site_packages) in paths
    assert str(project) in paths


def test_pcell_runner_loads_source_with_package_context(tmp_path: Path):
    package = tmp_path / "devices"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "constants.py").write_text("DEVICE_NAME = 'relative import worked'\n", encoding="utf-8")
    source = package / "capacitor.py"
    source.write_text(
        "from .constants import DEVICE_NAME\n"
        "class Capacitor:\n"
        "    imported_name = DEVICE_NAME\n",
        encoding="utf-8",
    )
    (tmp_path / "pya.py").write_text(
        "class Cell:\n"
        "    def cell_index(self): return 1\n"
        "class Top:\n"
        "    def insert(self, instance): pass\n"
        "class Layout:\n"
        "    def register_pcell(self, name, declaration):\n"
        "        assert declaration.imported_name == 'relative import worked'\n"
        "    def create_cell(self, name, values=None):\n"
        "        return Top() if name == 'VERIFY_TOP' else Cell()\n"
        "    def write(self, output): open(output, 'w').write('layout')\n"
        "class CellInstArray:\n"
        "    def __init__(self, *args): pass\n"
        "class Trans: pass\n",
        encoding="utf-8",
    )
    runner = tmp_path / "instantiate.py"
    runner.write_text(_RUNNER, encoding="utf-8")
    output = tmp_path / "output.gds"
    environment = os.environ.copy()
    environment.update({
        "PCELL_VERIFY_SOURCE": str(source),
        "PCELL_VERIFY_CLASS": "Capacitor",
        "PCELL_VERIFY_PARAMETERS": "{}",
        "PCELL_VERIFY_OUTPUT": str(output),
    })

    completed = subprocess.run(
        [sys.executable, str(runner)], capture_output=True, text=True, env=environment
    )

    assert completed.returncode == 0, completed.stderr
    assert output.read_text(encoding="utf-8") == "layout"


def test_pcell_runner_removes_paths_for_an_incompatible_python(tmp_path: Path):
    incompatible = tmp_path / "lib" / "python9.9" / "site-packages"
    incompatible.mkdir(parents=True)
    source = tmp_path / "device.py"
    source.write_text(
        "import sys\n"
        "class Device:\n"
        f"    incompatible_path_visible = {str(incompatible)!r} in sys.path\n",
        encoding="utf-8",
    )
    (tmp_path / "pya.py").write_text(
        "class Cell:\n"
        "    def cell_index(self): return 1\n"
        "class Top:\n"
        "    def insert(self, instance): pass\n"
        "class Layout:\n"
        "    def register_pcell(self, name, declaration):\n"
        "        assert not declaration.incompatible_path_visible\n"
        "    def create_cell(self, name, values=None):\n"
        "        return Top() if name == 'VERIFY_TOP' else Cell()\n"
        "    def write(self, output): open(output, 'w').write('layout')\n"
        "class CellInstArray:\n"
        "    def __init__(self, *args): pass\n"
        "class Trans: pass\n",
        encoding="utf-8",
    )
    runner = tmp_path / "instantiate.py"
    runner.write_text(_RUNNER, encoding="utf-8")
    output = tmp_path / "output.gds"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(incompatible)])
    environment.update({
        "PCELL_VERIFY_SOURCE": str(source),
        "PCELL_VERIFY_CLASS": "Device",
        "PCELL_VERIFY_PARAMETERS": "{}",
        "PCELL_VERIFY_OUTPUT": str(output),
    })

    completed = subprocess.run(
        [sys.executable, str(runner)], capture_output=True, text=True, env=environment
    )

    assert completed.returncode == 0, completed.stderr
    assert output.read_text(encoding="utf-8") == "layout"


def test_pcell_runner_rejects_errors_rendered_on_klayout_error_layer(tmp_path: Path):
    source = tmp_path / "device.py"
    source.write_text("class Device: pass\n", encoding="utf-8")
    (tmp_path / "pya.py").write_text(
        "class Text:\n"
        "    string = 'produce_impl failed: bad geometry'\n"
        "class Shape:\n"
        "    text = Text()\n"
        "    def is_text(self): return True\n"
        "class Shapes:\n"
        "    def each(self): return iter([Shape()])\n"
        "class Cell:\n"
        "    def shapes(self, layer): return Shapes()\n"
        "    def cell_index(self): return 1\n"
        "class Layout:\n"
        "    def __init__(self): self.cell = Cell()\n"
        "    def register_pcell(self, name, declaration): pass\n"
        "    def create_cell(self, name, values=None): return self.cell\n"
        "    def error_layer(self): return 99\n"
        "    def each_cell(self): return iter([self.cell])\n"
        "class CellInstArray:\n"
        "    def __init__(self, *args): pass\n"
        "class Trans: pass\n",
        encoding="utf-8",
    )
    runner = tmp_path / "instantiate.py"
    runner.write_text(_RUNNER, encoding="utf-8")
    output = tmp_path / "output.gds"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(tmp_path)
    environment.update({
        "PCELL_VERIFY_SOURCE": str(source),
        "PCELL_VERIFY_CLASS": "Device",
        "PCELL_VERIFY_PARAMETERS": "{}",
        "PCELL_VERIFY_OUTPUT": str(output),
    })

    completed = subprocess.run(
        [sys.executable, str(runner)], capture_output=True, text=True, env=environment
    )

    assert completed.returncode != 0
    assert "PCell generation failed" in completed.stderr
    assert "produce_impl failed: bad geometry" in completed.stderr
    assert not output.exists()


def test_violation_count_accepts_namespaces_and_item_attributes(tmp_path: Path):
    report = tmp_path / "report.lyrdb"
    report.write_text(
        '<report-database xmlns="urn:klayout"><items>'
        '<item id="1"/><item><category>spacing</category></item>'
        '</items></report-database>',
        encoding="utf-8",
    )

    assert KLayoutVerifier._violation_count(report) == 2
