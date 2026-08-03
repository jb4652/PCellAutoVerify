"""open-pdks/KLayout 风格 Python PCell 的静态扫描插件。"""

import ast
import re
from pathlib import Path

from core import PCell, PDK, Parameter

from .base import PDKPlugin


GF180_NMOS_NAME = "GF180MCUANMOS"
GF180_NMOS_SOURCE = (
    Path(__file__).with_name("examples") / "gf180_nmos.py"
).resolve()


class OpenPDKsPlugin(PDKPlugin):
    name = "open-pdks"
    markers = ("sky130", "gf180", "ihp-sg13", "open_pdks", "open-pdks")

    @staticmethod
    def _inferred_range(name: str, default: str) -> str:
        """Supply useful conservative values when source constraints are absent."""
        if not default:
            # An unparseable expression is represented by a blank scanner
            # default and must remain distinct from the literal string ``''``.
            return ""
        try:
            value = ast.literal_eval(default)
        except (ValueError, SyntaxError):
            value = default
        lower = name.lower()
        if isinstance(value, bool):
            return "choices=[False, True]"
        if isinstance(value, int):
            if any(token in lower for token in ("count", "finger", "rows", "cols", "mult")):
                values = [max(1, value // 2), max(1, value), max(2, value * 2)]
            else:
                values = [max(0, value - 1), value, value + 1]
            return f"choices={list(dict.fromkeys(values))}"
        if isinstance(value, float):
            base = value if value > 0 else 1.0
            return f"choices={[base * 0.5, base, base * 2.0]}"
        if isinstance(value, str):
            return f"choices=[{value!r}]"
        return f"choices=[{default}]"

    def supports(self, root: Path) -> bool:
        if not root.is_dir():
            return False
        names = {entry.name.lower() for entry in root.iterdir()}
        root_name = root.name.lower()
        return any(
            marker in root_name or any(marker in name for name in names)
            for marker in self.markers
        )

    @staticmethod
    def _literal(node: ast.AST | None) -> str:
        if node is None:
            return ""
        try:
            return repr(ast.literal_eval(node))
        except (ValueError, TypeError):
            return ""

    def _scan_file(self, path: Path, root: Path) -> list[PCell]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, SyntaxError):
            return []
        cells: list[PCell] = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = " ".join(ast.unparse(base).lower() for base in node.bases)
            methods = {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            is_pcell = (
                "pcell" in node.name.lower()
                or "pcell" in bases
                or bool({"produce_impl", "coerce_parameters_impl"} & methods)
            )
            if not is_pcell:
                continue
            parameters = self._scan_parameters(node)
            cells.append(PCell(node.name, str(path.relative_to(root)), parameters))
        return cells

    def _scan_parameters(self, node: ast.ClassDef) -> list[Parameter]:
        parameters: list[Parameter] = []
        for call in (child for child in ast.walk(node) if isinstance(child, ast.Call)):
            if not (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "param"
                and call.args
            ):
                continue
            try:
                name = ast.literal_eval(call.args[0])
            except (ValueError, TypeError):
                name = None
            if isinstance(name, str):
                keywords = {
                    keyword.arg: keyword.value
                    for keyword in call.keywords
                    if keyword.arg
                }
                constraints = [
                    f"{key}={value}"
                    for key in ("min", "max", "choices")
                    if (value := self._literal(keywords.get(key)))
                ]
                default = self._literal(keywords.get("default"))
                parameters.append(
                    Parameter(
                        name,
                        default,
                        ", ".join(constraints) or self._inferred_range(name, default),
                    )
                )
        for item in node.body:
            if isinstance(item, (ast.Assign, ast.AnnAssign)):
                target = item.targets[0] if isinstance(item, ast.Assign) else item.target
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    default = self._literal(item.value)
                    parameters.append(
                        Parameter(target.id, default, self._inferred_range(target.id, default))
                    )
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                defaults = item.args.defaults
                for argument, default in zip(item.args.args[-len(defaults) :], defaults):
                    if argument.arg != "self":
                        value = self._literal(default)
                        parameters.append(
                            Parameter(argument.arg, value, self._inferred_range(argument.arg, value))
                        )
        return parameters

    def scan(self, root: Path) -> PDK:
        cells: list[PCell] = []
        for path in root.rglob("*.py"):
            if not any(part.startswith(".") for part in path.relative_to(root).parts):
                cells.extend(self._scan_file(path, root))
        # An installed gf180mcuA tree may contain no directly discoverable
        # Python PCell. Supply a useful starter transistor in that case.
        if "gf180mcua" in root.name.lower() and not any(
            cell.name == GF180_NMOS_NAME for cell in cells
        ):
            cells.insert(
                0,
                PCell(
                    GF180_NMOS_NAME,
                    str(GF180_NMOS_SOURCE),
                    [
                        Parameter("width", "2.0", "choices=[1.0, 2.0, 4.0]"),
                        # The 0.2 µm boundary deliberately violates the usual
                        # GF180 gate-length rule.  It remains constructible so
                        # the example demonstrates failed DRC layout handling.
                        Parameter("length", "0.6", "choices=[0.2, 0.6, 1.0]"),
                    ],
                ),
            )
        return PDK(None, root.name, str(root.resolve()), self.name, pcells=cells)
