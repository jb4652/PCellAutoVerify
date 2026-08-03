"""从 PCell 参数约束生成一组规模可控的测试点。"""

from __future__ import annotations

import ast
import re

from .models import PCell, Parameter


def _display(value: object) -> str:
    """Keep generated values consistent with the strings shown in the UI."""
    return repr(value) if isinstance(value, str) else str(value)


def _literal(value: str) -> object:
    value = value.strip()
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value


def parameter_values(parameter: Parameter) -> list[str]:
    """Return representative values for a parameter's range expression.

    Supported forms are the scanner's ``min=..., max=..., choices=...`` form,
    a compact ``low..high`` form, and a comma-separated list.
    """
    value_range = parameter.value_range.strip()
    values: list[object] = []

    choices = re.search(r"(?:^|,)\s*choices\s*=\s*(.+)$", value_range)
    if choices:
        parsed = _literal(choices.group(1))
        if isinstance(parsed, (list, tuple, set)):
            values.extend(parsed)
    else:
        minimum = re.search(r"(?:^|,)\s*min\s*=\s*([^,]+)", value_range)
        maximum = re.search(r"(?:^|,)\s*max\s*=\s*([^,]+)", value_range)
        if minimum:
            values.append(_literal(minimum.group(1)))
        if parameter.default.strip():
            values.append(_literal(parameter.default))
        if maximum:
            values.append(_literal(maximum.group(1)))

        if not minimum and not maximum and ".." in value_range:
            low, high = value_range.split("..", 1)
            values = [_literal(low)]
            if parameter.default.strip():
                values.append(_literal(parameter.default))
            values.append(_literal(high))
        elif not minimum and not maximum and value_range:
            values = [_literal(item) for item in value_range.split(",")]

    if not values and parameter.default.strip():
        values.append(_literal(parameter.default))

    result: list[str] = []
    for value in values:
        rendered = _display(value)
        if rendered and rendered not in result:
            result.append(rendered)
    return result


def generate_test_points(pcell: PCell, limit: int = 100) -> list[dict[str, str]]:
    """Generate a baseline point plus one-parameter-at-a-time variations.

    This avoids the combinatorial explosion of a full Cartesian product while
    still exercising every representative boundary or choice.
    """
    if limit <= 0 or not pcell.parameters:
        return []

    candidates = [parameter_values(parameter) for parameter in pcell.parameters]
    baseline = {
        parameter.name: (values[0] if values else "")
        for parameter, values in zip(pcell.parameters, candidates)
    }
    points = [baseline]
    for parameter, values in zip(pcell.parameters, candidates):
        for value in values[1:]:
            point = baseline.copy()
            point[parameter.name] = value
            if point not in points:
                points.append(point)
            if len(points) >= limit:
                return points
    return points
