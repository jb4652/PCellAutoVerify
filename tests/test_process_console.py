import sys

from core.process_console import capture_process_console, run_process


def test_console_records_command_working_directory_and_both_streams(tmp_path):
    messages = []
    command = [sys.executable, "-c", "import sys; print('output'); print('warning', file=sys.stderr); sys.exit(3)"]
    with capture_process_console(messages.append):
        result = run_process(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 3
    assert str(tmp_path) in messages[0]
    assert sys.executable in messages[0]
    assert "[stdout]\noutput" in messages[1]
    assert "[stderr]\nwarning" in messages[2]
    assert messages[3] == "[exit: 3]"
