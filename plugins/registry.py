"""插件注册与选择。"""

from pathlib import Path

from core import PDK

from .base import PDKPlugin
from .open_pdks import OpenPDKsPlugin


class PluginRegistry:
    def __init__(self, plugins: list[PDKPlugin] | None = None):
        self.plugins = plugins if plugins is not None else [OpenPDKsPlugin()]

    def import_path(self, path: Path) -> PDK:
        for plugin in self.plugins:
            if plugin.supports(path):
                return plugin.scan(path)
        raise ValueError("没有插件支持所选 PDK 目录。")
