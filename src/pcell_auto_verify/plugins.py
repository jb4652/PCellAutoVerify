import ast
from abc import ABC, abstractmethod
from pathlib import Path

from .models import PCell, PDK, Parameter


class PDKPlugin(ABC):
    name: str

    @abstractmethod
    def supports(self, root: Path) -> bool: ...

    @abstractmethod
    def scan(self, root: Path) -> PDK: ...


class OpenPDKsPlugin(PDKPlugin):
    name = "open-pdks"
    markers = ("sky130", "gf180", "ihp-sg13", "open_pdks", "open-pdks")

    def supports(self, root: Path) -> bool:
        if not root.is_dir():
            return False
        names = {entry.name.lower() for entry in root.iterdir()}
        root_name = root.name.lower()
        return any(marker in root_name or any(marker in name for name in names) for marker in self.markers)

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
        cells = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = " ".join(ast.unparse(base).lower() for base in node.bases)
            methods = {item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
            is_pcell = "pcell" in node.name.lower() or "pcell" in bases or {"produce_impl", "coerce_parameters_impl"} & methods
            if not is_pcell:
                continue
            params = []
            # KLayout PCells commonly declare parameters with
            # self.param("w", TypeDouble, "Width", default=1.0, ...).
            for call in (child for child in ast.walk(node) if isinstance(child, ast.Call)):
                if not (isinstance(call.func, ast.Attribute) and call.func.attr == "param" and call.args):
                    continue
                try:
                    param_name = ast.literal_eval(call.args[0])
                except (ValueError, TypeError):
                    param_name = None
                if isinstance(param_name, str):
                    keywords = {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg}
                    default = self._literal(keywords.get("default"))
                    constraints = []
                    for key in ("min", "max", "choices"):
                        value = self._literal(keywords.get(key))
                        if value:
                            constraints.append(f"{key}={value}")
                    params.append(Parameter(param_name, default, ", ".join(constraints)))
            for item in node.body:
                if isinstance(item, (ast.Assign, ast.AnnAssign)):
                    target = item.targets[0] if isinstance(item, ast.Assign) else item.target
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        params.append(Parameter(target.id, self._literal(item.value)))
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    for arg, default in zip(item.args.args[-len(item.args.defaults):], item.args.defaults):
                        if arg.arg != "self":
                            params.append(Parameter(arg.arg, self._literal(default)))
            cells.append(PCell(node.name, str(path.relative_to(root)), params))
        return cells

    def scan(self, root: Path) -> PDK:
        cells = []
        for path in root.rglob("*.py"):
            if not any(part.startswith(".") for part in path.relative_to(root).parts):
                cells.extend(self._scan_file(path, root))
        return PDK(None, root.name, str(root.resolve()), self.name, pcells=cells)


class PluginRegistry:
    def __init__(self, plugins: list[PDKPlugin] | None = None):
        self.plugins = plugins or [OpenPDKsPlugin()]

    def import_path(self, path: Path) -> PDK:
        for plugin in self.plugins:
            if plugin.supports(path):
                return plugin.scan(path)
        raise ValueError("没有插件支持所选 PDK 目录。")
