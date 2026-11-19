"""Load the installed Sky130A KLayout PCell library in a worker process."""

import inspect
import json
import sys
from pathlib import Path


SKY130_PYTHON_PATH = Path("libs.tech/klayout/python")


def is_sky130a(name: str) -> bool:
    return name.casefold() == "sky130a"


def load_library(python_dir: Path):
    import klayout.db as kdb

    sys.modules.setdefault("pya", kdb)
    sys.path.insert(0, str(python_dir))
    from cells import sky130

    library = sky130()
    if isinstance(library, kdb.Library):
        return library
    for name in kdb.Library.library_names():
        if "sky130" in name.casefold() or "skywater" in name.casefold():
            return kdb.Library.library_by_name(name)
    raise ValueError("Sky130A did not register a KLayout library")


def _parameter_data(parameter) -> dict[str, str | bool]:
    choices = parameter.choice_values()
    limits = [
        f"{name}={value!r}"
        for name, value in (("min", parameter.min_value), ("max", parameter.max_value))
        if value is not None
    ]
    if choices and all(isinstance(value, (str, int, float, bool)) for value in choices):
        limits.append(f"choices={choices!r}")
    default = parameter.default
    return {
        "name": parameter.name,
        "default": repr(default) if isinstance(default, (str, int, float, bool)) else "",
        "value_range": ", ".join(limits),
        "description": parameter.description or "",
        "hidden": parameter.hidden,
        "readonly": parameter.readonly,
    }


if __name__ == "__main__":
    root = Path(sys.argv[1])
    library = load_library(root / SKY130_PYTHON_PATH)
    layout = library.layout()
    names = sorted(layout.pcell_names())
    if not names:
        raise ValueError("Sky130A did not register any KLayout PCells")
    data = []
    for name in names:
        declaration = layout.pcell_declaration(name)
        try:
            source = Path(inspect.getfile(type(declaration))).absolute()
        except (OSError, TypeError):
            source = None
        if source is not None and source.is_file():
            if source.is_relative_to(root):
                source = source.relative_to(root)
        else:
            source = None
        data.append({
            "name": name,
            "source": str(source) if source is not None else "",
            "parameters": [
                _parameter_data(parameter)
                for parameter in declaration.get_parameters()
            ],
        })
    Path(sys.argv[2]).write_text(json.dumps(data), encoding="utf-8")
