from typing import List, Dict, Any, Optional
from pathlib import Path
import yaml

from semantic_reliability.assertions.base import DataAssertion
from semantic_reliability.assertions.structural import (
    NonNullOutputAssertion,
    UniqueKeyAssertion,
    RowCountBoundsAssertion,
    AcceptedRangeAssertion,
    AcceptedValuesAssertion,
    RelationshipsAssertion,
    SingularSqlAssertion,
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
            elif a_type in ("accepted_range", "range", "dbt_utils.accepted_range"):
                suite.add(AcceptedRangeAssertion(
                    column=a_conf.get("column", ""),
                    min_value=a_conf.get("min_value"),
                    max_value=a_conf.get("max_value"),
                    inclusive=a_conf.get("inclusive", True),
                    name=name,
                ))
            elif a_type in ("accepted_values", "categorical_set", "domain"):
                suite.add(AcceptedValuesAssertion(
                    column=a_conf.get("column", ""),
                    values=a_conf.get("values", []),
                    quote=a_conf.get("quote", True),
                    name=name,
                ))
            elif a_type in ("relationships", "foreign_key", "referential_integrity"):
                suite.add(RelationshipsAssertion(
                    from_column=a_conf.get("from_column") or a_conf.get("column", ""),
                    to_table=a_conf.get("to_table", ""),
                    to_column=a_conf.get("to_column") or a_conf.get("field", ""),
                    name=name,
                ))
            elif a_type in ("singular_sql_test", "singular_test", "singular_sql", "custom_sql"):
                suite.add(SingularSqlAssertion(
                    name=a_conf.get("name", "singular_sql_test"),
                    sql=a_conf.get("sql", ""),
                    description=a_conf.get("description"),
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
        """Default Tier-1 baseline suite mimicking standard minimal dbt test suite (nulls + uniqueness + row count)."""
        suite = cls(name="Standard_dbt_Structural_Suite")
        suite.add(NonNullOutputAssertion(columns=["customer_id", "reporting_month", "net_revenue"]))
        suite.add(UniqueKeyAssertion(columns=["customer_id", "reporting_month"]))
        suite.add(RowCountBoundsAssertion(min_rows=1))
        return suite

    @classmethod
    def get_realistic_dbt_suite(cls) -> "AssertionSuite":
        """Default Tier-2 realistic dbt test suite sourced from dbt-labs/jaffle_shop reference project."""
        yaml_path = Path(__file__).resolve().parent.parent.parent / "examples" / "assertions" / "realistic_dbt_suite.yaml"
        if yaml_path.exists():
            return cls.from_yaml_file(yaml_path)

        suite = cls(name="Realistic_dbt_Suite")
        suite.add(NonNullOutputAssertion(columns=["order_id", "customer_id", "amount"]))
        suite.add(UniqueKeyAssertion(columns=["order_id"]))
        suite.add(RowCountBoundsAssertion(min_rows=1))
        suite.add(AcceptedRangeAssertion(column="amount", min_value=0.0))
        suite.add(AcceptedValuesAssertion(column="status", values=["placed", "shipped", "completed", "return_pending", "returned"]))
        suite.add(RelationshipsAssertion(from_column="customer_id", to_table="customers", to_column="customer_id"))
        suite.add(SingularSqlAssertion(
            name="assert_positive_total_for_payments",
            sql="SELECT order_id, SUM(amount) AS total_amount FROM {{ model }} GROUP BY 1 HAVING NOT(SUM(amount) >= 0)"
        ))
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

