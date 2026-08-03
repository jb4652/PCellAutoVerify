"""插件协议。"""

from abc import ABC, abstractmethod
from pathlib import Path

from core import PDK


class PDKPlugin(ABC):
    name: str

    @abstractmethod
    def supports(self, root: Path) -> bool:
        """返回该插件是否可以处理目录。"""

    @abstractmethod
    def scan(self, root: Path) -> PDK:
        """扫描目录并返回 PDK 元数据。"""
