from pathlib import Path
from unittest.mock import patch

from core import KLayoutVerifier, PCell


def test_pcell_runner_uses_environment_instead_of_unsupported_separator(tmp_path: Path):
    pdk_root = tmp_path / "pdk"
    pdk_root.mkdir()
    (pdk_root / "device.py").write_text("class Device: pass\n", encoding="utf-8")
    (pdk_root / "checks.lydrc").write_text("# DRC deck\n", encoding="utf-8")
    output_root = tmp_path / "output"
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if Path(command[command.index("-r") + 1]).name == "instantiate.py":
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
    assert generation_command == [
        "/usr/bin/klayout", "-b", "-r", str(output_root / "instantiate.py")
    ]
    assert "--" not in generation_command
    assert generation_options["env"]["PCELL_VERIFY_CLASS"] == "Device"
    assert generation_options["env"]["PCELL_VERIFY_PARAMETERS"] == '{"width": 1.5}'
    assert results[0].passed
