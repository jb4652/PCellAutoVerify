from core import PCell, Parameter, generate_test_points, parameter_values


def test_parameter_values_support_scanner_constraints_and_choices():
    assert parameter_values(Parameter("w", "2", "min=1, max=3")) == ["1", "2", "3"]
    assert parameter_values(Parameter("layer", "", "choices=['M1', 'M2']")) == [
        "'M1'",
        "'M2'",
    ]


def test_generate_points_builds_cartesian_matrix():
    pcell = PCell(
        "Device",
        "device.py",
        [Parameter("w", "2", "1..3"), Parameter("fingers", "4", "2, 4, 8")],
    )

    assert generate_test_points(pcell) == [
        {"w": "1", "fingers": "2"},
        {"w": "1", "fingers": "4"},
        {"w": "1", "fingers": "8"},
        {"w": "2", "fingers": "2"},
        {"w": "2", "fingers": "4"},
        {"w": "2", "fingers": "8"},
        {"w": "3", "fingers": "2"},
        {"w": "3", "fingers": "4"},
        {"w": "3", "fingers": "8"},
    ]
    assert generate_test_points(PCell("Simple", "x.py", [Parameter("w", "2")])) == [
        {"w": "2"}
    ]
