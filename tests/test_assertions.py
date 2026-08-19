import pytest
import duckdb
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
from semantic_reliability.assertions.registry import AssertionSuite
from semantic_reliability.harness.duckdb_runner import DuckDBFixtureRunner


def test_non_null_assertion():
    runner = DuckDBFixtureRunner()
    good_sql = "SELECT 'C1' AS customer_id, 100.0 AS amount"
    bad_sql = "SELECT NULL AS customer_id, 100.0 AS amount"

    a = NonNullOutputAssertion(columns=["customer_id"])
    assert a.evaluate(runner.con, good_sql).passed is True
    assert a.evaluate(runner.con, bad_sql).passed is False


def test_unique_key_assertion():
    runner = DuckDBFixtureRunner()
    good_sql = "SELECT 'C1' AS id UNION ALL SELECT 'C2' AS id"
    bad_sql = "SELECT 'C1' AS id UNION ALL SELECT 'C1' AS id"

    a = UniqueKeyAssertion(columns=["id"])
    assert a.evaluate(runner.con, good_sql).passed is True
    assert a.evaluate(runner.con, bad_sql).passed is False


def test_row_count_bounds_assertion():
    runner = DuckDBFixtureRunner()
    sql = "SELECT 1 AS x UNION ALL SELECT 2 AS x"

    a_pass = RowCountBoundsAssertion(min_rows=1, max_rows=5)
    a_fail = RowCountBoundsAssertion(min_rows=5)
    assert a_pass.evaluate(runner.con, sql).passed is True
    assert a_fail.evaluate(runner.con, sql).passed is False


def test_required_population_assertion():
    runner = DuckDBFixtureRunner()
    # Good query filters status = 'active'
    good_sql = "SELECT customer_id FROM transactions WHERE status = 'active'"
    # Bad query leaks inactive/pending records (like C3 which is pending)
    bad_sql = "SELECT customer_id FROM transactions"

    a = RequiredPopulationAssertion(source_table="transactions", required_filter="status = 'active'")
    assert a.evaluate(runner.con, good_sql).passed is True
    assert a.evaluate(runner.con, bad_sql).passed is False


def test_metric_value_assertion():
    runner = DuckDBFixtureRunner()
    sql = "SELECT 100.0 AS net_revenue UNION ALL SELECT 50.0 AS net_revenue"

    a_pass = MetricValueAssertion(column="net_revenue", expected_value=150.0)
    a_fail = MetricValueAssertion(column="net_revenue", expected_value=500.0)
    assert a_pass.evaluate(runner.con, sql).passed is True
    assert a_fail.evaluate(runner.con, sql).passed is False


def test_assertion_suite_from_yaml(tmp_path):
    yaml_content = """
    suite_name: test_suite
    assertions:
      - type: not_null
        columns: [customer_id]
      - type: row_count_bounds
        min_rows: 1
    """
    f = tmp_path / "suite.yaml"
    f.write_text(yaml_content, encoding="utf-8")

    suite = AssertionSuite.from_yaml_file(f)
    assert suite.name == "test_suite"
    assert len(suite.assertions) == 2
