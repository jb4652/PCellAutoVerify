"""从 PCell 参数约束生成一组规模可控的测试点。"""

from __future__ import annotations

import ast
import itertools
import math
import re

from .models import PCell, Parameter


def inferred_range(parameter: Parameter) -> str:
    """Return a small, concrete range when a scanner supplied no constraint."""
    default = _literal(parameter.default)
    name = parameter.name.lower()
    if isinstance(default, bool):
        return "choices=[False, True]"
    if isinstance(default, int):
        if any(word in name for word in ("count", "finger", "row", "col", "mult")):
            low, high = max(1, default // 2), max(2, default * 2)
        else:
            low, high = max(0, default - 1), default + 1
        return f"min={low}, max={high}"
    if isinstance(default, float):
        scale = abs(default) or 1.0
        low = max(0.0, default - scale * 0.5)
        high = default + scale
        return f"min={low:g}, max={high:g}"
    return ""


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
    """Return the boundary values for a parameter's range expression.

    Supported forms are the scanner's ``min=..., max=..., choices=...`` form,
    a compact ``low..high`` form, and a comma-separated list.
    """
    value_range = parameter.value_range.strip() or inferred_range(parameter)
    values: list[object] = []

    choices = re.search(r"(?:^|,)\s*choices\s*=\s*(.+)$", value_range)
    if choices:
        parsed = _literal(choices.group(1))
        if isinstance(parsed, (list, tuple, set)):
            parsed = (
                sorted(parsed, key=_display)
                if isinstance(parsed, set)
                else list(parsed)
            )
            if parsed:
                values.extend((parsed[0], parsed[-1]))
    else:
        minimum = re.search(r"(?:^|,)\s*min\s*=\s*([^,]+)", value_range)
        maximum = re.search(r"(?:^|,)\s*max\s*=\s*([^,]+)", value_range)
        if minimum:
            values.append(_literal(minimum.group(1)))
        if maximum:
            values.append(_literal(maximum.group(1)))

        if not minimum and not maximum and ".." in value_range:
            low, high = value_range.split("..", 1)
            values = [_literal(low)]
            values.append(_literal(high))
        elif not minimum and not maximum and value_range:
            listed = [_literal(item) for item in value_range.split(",")]
            values = [listed[0], listed[-1]]

    if not values and parameter.default.strip():
        values.append(_literal(parameter.default))

    result: list[str] = []
    for value in values:
        rendered = _display(value)
        if rendered and rendered not in result:
            result.append(rendered)
    return result


def generate_test_points(pcell: PCell, limit: int = 200) -> list[dict[str, str]]:
    """Generate a deterministic Cartesian matrix from parameter boundaries."""
    if limit <= 0 or not pcell.parameters:
        return []

    # A blank scanner default means that the source expression could not be
    # evaluated statically; it does not mean that the PCell should receive an
    # empty string.  Leave such parameters out so KLayout uses the declaration's
    # own runtime default.  Passing ``""`` to a numeric TypeDouble/TypeInt is a
    # common cause of failures in ``coerce_parameters_impl``.
    concrete = [
        (parameter, values)
        for parameter in pcell.parameters
        if (values := parameter_values(parameter))
    ]
    if not concrete:
        return [{}]
    parameters, candidates = zip(*concrete)
    total = math.prod(len(values) for values in candidates)
    combinations = itertools.product(*candidates)
    if total <= limit:
        selected = combinations
    else:
        wanted = {round(i * (total - 1) / (limit - 1)) for i in range(limit)}
        selected = (values for index, values in enumerate(combinations) if index in wanted)
    return [
        {parameter.name: value for parameter, value in zip(parameters, values)}
        for values in selected
    ]
