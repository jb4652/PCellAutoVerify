"""Evaluate native PCell parameter callbacks without producing geometry."""

from .sky130_inverter import inverter_dimensions


def evaluate_callback(layout, declaration, changed: str, overrides: dict) -> dict:
    from klayout.db import PCellParameterStates

    definitions = declaration.get_parameters()
    states = PCellParameterStates()
    for parameter in definitions:
        state = states.parameter(parameter.name)
        state.value = overrides.get(parameter.name, parameter.default)
        state.visible = not parameter.hidden
        state.readonly = parameter.readonly

    declaration.callback(layout, changed, states)
    names = [parameter.name for parameter in definitions]
    defaults = {parameter.name: parameter.default for parameter in definitions}
    effective = declaration.coerce_parameters(
        layout, [states.parameter(name).value for name in names]
    )
    values = {}
    messages = []
    editable = {}
    for name, value in zip(names, effective, strict=True):
        state = states.parameter(name)
        if name in overrides or value != state.value or value != defaults[name]:
            if value is None:
                values[name] = ""
            elif isinstance(value, (bool, int, float, str)):
                values[name] = repr(value)
        if state.tooltip:
            messages.append(f"{name}: {state.tooltip}")
        editable[name] = state.enabled and state.visible and not state.readonly
    return {"values": values, "messages": messages, "editable": editable}


def evaluate_inverter_callback(overrides: dict) -> dict:
    return {
        "values": {key: repr(value) for key, value in inverter_dimensions(overrides, coerce=True).items()},
        "messages": [],
        "editable": {},
    }
