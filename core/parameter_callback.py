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

    names = [parameter.name for parameter in definitions]
    defaults = {parameter.name: parameter.default for parameter in definitions}
    initial = [states.parameter(name).value for name in names]
    print("[callback] PCellDeclaration.callback", flush=True)
    declaration.callback(layout, changed, states)
    after_callback = [states.parameter(name).value for name in names]
    _log_changes("callback", names, initial, after_callback)

    print("[coerce] PCellDeclaration.coerce_parameters", flush=True)
    effective = declaration.coerce_parameters(layout, list(after_callback))
    _log_changes("coerce", names, after_callback, effective)
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
        if state.tooltip:
            print(f"[callback hint] {name}: {state.tooltip}", flush=True)
    return {"values": values, "messages": messages, "editable": editable}


def _log_changes(stage, names, before, after):
    changes = [
        f"{name}: {old!r} → {new!r}"
        for name, old, new in zip(names, before, after, strict=True)
        if old != new
    ]
    print(f"[{stage}] " + ("; ".join(changes) if changes else "No value changes"), flush=True)


def evaluate_inverter_callback(layout, changed: str, overrides: dict) -> dict:
    from klayout.db import PCellDeclarationHelper

    defaults = inverter_dimensions({})

    class InverterParameters(PCellDeclarationHelper):
        def __init__(self):
            super().__init__()
            for name, default in defaults.items():
                self.param(name, self.TypeDouble, name, default=default, unit="µm")

        def callback_impl(self, name):
            state = getattr(self, name)
            corrected = inverter_dimensions({name: state.value}, coerce=True)[name]
            if corrected != state.value:
                state.tooltip = (
                    "The inverter uses minimum channel dimensions and a 0.005 µm grid."
                )

        def coerce_parameters_impl(self):
            values = {name: getattr(self, name) for name in defaults}
            for name, value in inverter_dimensions(values, coerce=True).items():
                setattr(self, name, value)

    print("[callback] Application-defined Sky130A inverter declaration", flush=True)
    return evaluate_callback(layout, InverterParameters(), changed, overrides)
