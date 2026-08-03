"""open-pdks/KLayout 风格 Python PCell 的静态扫描插件。"""

import ast
from pathlib import Path

from core import PCell, PDK, Parameter

from .base import PDKPlugin


class OpenPDKsPlugin(PDKPlugin):
    name = "open-pdks"
    markers = ("sky130", "gf180", "ihp-sg13", "open_pdks", "open-pdks")

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
                parameters.append(
                    Parameter(
                        name,
                        self._literal(keywords.get("default")),
                        ", ".join(constraints),
                    )
                )
        for item in node.body:
            if isinstance(item, (ast.Assign, ast.AnnAssign)):
                target = item.targets[0] if isinstance(item, ast.Assign) else item.target
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    parameters.append(Parameter(target.id, self._literal(item.value)))
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                defaults = item.args.defaults
                for argument, default in zip(item.args.args[-len(defaults) :], defaults):
                    if argument.arg != "self":
                        parameters.append(
                            Parameter(argument.arg, self._literal(default))
                        )
        return parameters

    def scan(self, root: Path) -> PDK:
        cells: list[PCell] = []
        for path in root.rglob("*.py"):
            if not any(part.startswith(".") for part in path.relative_to(root).parts):
                cells.extend(self._scan_file(path, root))
        return PDK(None, root.name, str(root.resolve()), self.name, pcells=cells)
