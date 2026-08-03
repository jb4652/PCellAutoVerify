"""不依赖界面和存储实现的领域模型。"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class Parameter:
    name: str
    default: str = ""
    value_range: str = ""


@dataclass(slots=True)
class VerificationResult:
    """The outcome and generated layout belonging to one test point."""

    index: int
    parameters: dict[str, str]
    passed: bool
    message: str
    layout_path: str = ""
    preview_path: str = ""


@dataclass(slots=True)
class PCell:
    name: str
    source: str
    parameters: list[Parameter] = field(default_factory=list)


@dataclass(slots=True)
class PDK:
    id: int | None
    name: str
    path: str
    plugin: str
    active: bool = False
    pcells: list[PCell] = field(default_factory=list)
