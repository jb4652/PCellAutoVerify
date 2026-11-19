from klayout import db as kdb

from core.parameter_callback import evaluate_callback


def test_native_callback_updates_value_hint_and_parameter_editability():
    class Device(kdb.PCellDeclarationHelper):
        def __init__(self):
            super().__init__()
            self.param("width", self.TypeDouble, "Width", default=0.42)
            self.param("spacing", self.TypeDouble, "Spacing", default=0.2)

        def callback_impl(self, name):
            assert name == "width"
            self.width.value = max(self.width.value, 0.42)
            self.width.tooltip = "Width was clamped"
            self.spacing.enabled = False

        def coerce_parameters_impl(self):
            self.spacing = max(self.spacing, 0.3)

    result = evaluate_callback(kdb.Layout(), Device(), "width", {"width": 0.10})
    assert result["values"] == {"width": "0.42", "spacing": "0.3"}
    assert result["messages"] == ["width: Width was clamped"]
    assert not result["editable"]["spacing"]
