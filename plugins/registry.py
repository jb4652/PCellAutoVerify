"""插件注册与选择。"""

from pathlib import Path

from core import PDK

from .base import PDKPlugin
from .open_pdks import OpenPDKsPlugin


class PluginRegistry:
    def __init__(self, plugins: list[PDKPlugin] | None = None):
        self.plugins = plugins if plugins is not None else [OpenPDKsPlugin()]

    def import_path(self, path: Path) -> PDK:
        selected = path.expanduser().absolute()
        try:
            root = selected.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError(f"无法打开 PDK 目录：{selected}") from error
        if not root.is_dir():
            raise ValueError(f"PDK 路径不是目录：{selected}")
        # Prefer a recognized name supplied by the user, such as a sky130A
        # symlink to an installation stored under a versioned directory.
        for plugin in self.plugins:
            if plugin.supports(selected):
                return plugin.scan(selected)
            if root != selected and plugin.supports(root):
                return plugin.scan(root)
        raise ValueError("没有插件支持所选 PDK 目录。")
