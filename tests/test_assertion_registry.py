import textwrap

from semantic_reliability.assertions.registry import AssertionSuite
from semantic_reliability.assertions.semantic import MetricValueAssertion


def test_metric_value_tolerance_is_parsed_from_yaml(tmp_path):
    yaml_path = tmp_path / "suite.yaml"
    yaml_path.write_text(textwrap.dedent("""
        suite_name: tolerance_suite
        assertions:
        - type: metric_value
          column: readmission_rate
          expected: 0.5
          tolerance_pct: 5.0
    """), encoding="utf-8")

    suite = AssertionSuite.from_yaml_file(yaml_path)
    assertion = next(a for a in suite.assertions if isinstance(a, MetricValueAssertion))
    assert assertion.expected_value == 0.5
    assert assertion.tolerance_pct == 5.0
