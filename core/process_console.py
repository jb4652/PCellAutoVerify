"""Optional console output for external EDA processes."""

import shlex
import subprocess
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path


_sink = ContextVar("process_console", default=None)
_CONTEXT_KEYS = (
    "PDK_ROOT",
    "PCELL_MAGIC_GDS", "PCELL_MAGIC_TOP", "PCELL_MAGIC_OUTPUT",
    "PCELL_VERIFY_SOURCE", "PCELL_VERIFY_LIBRARY", "PCELL_VERIFY_CLASS",
    "PCELL_VERIFY_PARAMETERS", "PCELL_VERIFY_OUTPUT", "PCELL_VERIFY_PREVIEW",
    "PCELL_VERIFY_CALLBACK",
)


@contextmanager
def capture_process_console(write):
    token = _sink.set(write)
    try:
        yield
    finally:
        _sink.reset(token)


def command_entry(command, cwd=None, env=None):
    directory = Path(cwd or Path.cwd()).absolute()
    context = [f"{key}={shlex.quote(env[key])}" for key in _CONTEXT_KEYS if env and key in env]
    return "\n".join([f"[cwd: {directory}]", "$ " + " ".join([*context, shlex.join(command)])])


def _stream(label, value):
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    return f"[{label}]\n{value}" if value else ""


def run_process(command, **kwargs):
    """Preserve subprocess.run behavior and mirror captured output to the active console."""
    write = _sink.get()
    if write is None:
        return subprocess.run(command, **kwargs)

    write(command_entry(command, kwargs.get("cwd"), kwargs.get("env")))
    try:
        result = subprocess.run(command, **kwargs)
    except (OSError, subprocess.SubprocessError) as error:
        for label in ("stdout", "stderr"):
            if entry := _stream(label, getattr(error, label, None)):
                write(entry)
        write(f"[process error: {error}]")
        raise

    for label in ("stdout", "stderr"):
        if entry := _stream(label, getattr(result, label, None)):
            write(entry)
    write(f"[exit: {result.returncode}]")
    return result
