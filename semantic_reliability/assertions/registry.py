from typing import List, Dict, Any, Optional
from pathlib import Path
import yaml

from semantic_reliability.assertions.base import DataAssertion
from semantic_reliability.assertions.structural import (
    NonNullOutputAssertion,
    UniqueKeyAssertion,
    RowCountBoundsAssertion,
)
from semantic_reliability.assertions.semantic import (
    RequiredPopulationAssertion,
    MetricValueAssertion,
    ExpectedGrainAssertion,
)


class AssertionSuite:
    """A collection of data quality and semantic assertions."""

    def __init__(self, name: str, assertions: Optional[List[DataAssertion]] = None):
        self.name = name
        self.assertions: List[DataAssertion] = assertions or []

    def add(self, assertion: DataAssertion) -> "AssertionSuite":
        self.assertions.append(assertion)
        return self

    @classmethod
    def from_yaml_file(cls, yaml_path: str | Path) -> "AssertionSuite":
        """Load an assertion suite from YAML configuration."""
        content = Path(yaml_path).read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        suite_name = data.get("suite_name", Path(yaml_path).stem)
        suite = cls(name=suite_name)

        for a_conf in data.get("assertions", []):
            a_type = a_conf.get("type", "").lower()
            name = a_conf.get("name")

            if a_type in ("not_null", "non_null"):
                suite.add(NonNullOutputAssertion(columns=a_conf.get("columns", []), name=name))
            elif a_type in ("unique", "unique_key"):
                suite.add(UniqueKeyAssertion(columns=a_conf.get("columns", []), name=name))
            elif a_type in ("row_count", "row_count_bounds"):
                suite.add(RowCountBoundsAssertion(
                    min_rows=a_conf.get("min_rows", 1),
                    max_rows=a_conf.get("max_rows"),
                    name=name
                ))
            elif a_type in ("population", "required_population", "required_filter"):
                suite.add(RequiredPopulationAssertion(
                    source_table=a_conf.get("source_table", "transactions"),
                    required_filter=a_conf.get("expression") or a_conf.get("required_filter", "1=1"),
                    join_key=a_conf.get("join_key", "customer_id"),
                    name=name,
                ))
            elif a_type in ("metric_value", "expected_value"):
                suite.add(MetricValueAssertion(
                    column=a_conf.get("column", "net_revenue"),
                    expected_value=a_conf.get("expected") or a_conf.get("expected_value"),
                    min_value=a_conf.get("min_value"),
                    max_value=a_conf.get("max_value"),
                    name=name,
                ))
            elif a_type in ("grain", "expected_grain"):
                suite.add(ExpectedGrainAssertion(
                    grain_columns=a_conf.get("columns") or a_conf.get("grain_columns", []),
                    name=name,
                ))

        return suite

    @classmethod
    def get_standard_structural_suite(cls) -> "AssertionSuite":
        """Default baseline suite mimicking standard dbt test suite (nulls + uniqueness + row count)."""
        suite = cls(name="Standard_dbt_Structural_Suite")
        suite.add(NonNullOutputAssertion(columns=["customer_id", "reporting_month", "net_revenue"]))
        suite.add(UniqueKeyAssertion(columns=["customer_id", "reporting_month"]))
        suite.add(RowCountBoundsAssertion(min_rows=1))
        return suite

    @classmethod
    def get_semantic_assertion_suite(cls) -> "AssertionSuite":
        """Comprehensive semantic assertion suite enforcing population, grain, and values."""
        suite = cls(name="Semantic_Reliability_Suite")
        # Include structural checks
        suite.add(NonNullOutputAssertion(columns=["customer_id", "reporting_month", "net_revenue"]))
        suite.add(ExpectedGrainAssertion(grain_columns=["customer_id", "reporting_month"]))
        # Include semantic business checks
        suite.add(RequiredPopulationAssertion(
            source_table="transactions",
            required_filter="status = 'active'",
            join_key="customer_id"
        ))
        suite.add(RequiredPopulationAssertion(
            source_table="transactions",
            required_filter="region = 'NA'",
            join_key="customer_id"
        ))
        suite.add(MetricValueAssertion(
            column="net_revenue",
            expected_value=3000.0,
            tolerance_pct=5.0
        ))
        return suite
