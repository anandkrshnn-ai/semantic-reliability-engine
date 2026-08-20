from pathlib import Path
import pytest
import pandas as pd
import duckdb

from semantic_reliability.harness.baseline_ladder import BaselineLadderEvaluator, BaselineTier
from semantic_reliability.compiler.compiler import MetricCompiler
from semantic_reliability.assertions.registry import AssertionSuite
from semantic_reliability.assertions.structural import (
    AcceptedRangeAssertion,
    AcceptedValuesAssertion,
    RelationshipsAssertion,
    SingularSqlAssertion,
)

SAMPLE_CONTRACT_YAML = """
metric: net_revenue
owner: finance
grain: customer_month
invariants:
  population:
    required_filters:
      - "status = 'active'"
  grain:
    required_dimensions:
      - customer_id
      - "date_trunc('month', transaction_date)"
  aggregation:
    required_function: SUM
    positive_components:
      - "type = 'invoice'"
    negative_components:
      - "type = 'refund'"
sql: |
  SELECT
    customer_id,
    DATE_TRUNC('month', transaction_date) AS reporting_month,
    SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
    SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
  FROM transactions
  WHERE status = 'active'
  GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
"""


def test_baseline_ladder_tier_0_and_tier_1():
    comp = MetricCompiler.from_yaml_str(SAMPLE_CONTRACT_YAML)
    ladder = BaselineLadderEvaluator(contract=comp.definition)

    valid_sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1"
    t0 = ladder.evaluate_tier_0_syntax(valid_sql)
    assert t0["passed"] is True

    df = pd.DataFrame([{"customer_id": "C1", "net_revenue": 100.0}])
    t1 = ladder.evaluate_tier_1_minimal_structural(df)
    assert t1["passed"] is True


def test_baseline_ladder_tier_2_accepted_range_dynamic():
    ladder = BaselineLadderEvaluator()
    suite = AssertionSuite(name="custom_range_suite")
    suite.add(AcceptedRangeAssertion(column="amount", min_value=10.0, max_value=1000.0))

    df_valid = pd.DataFrame([{"order_id": "O1", "amount": 50.0}])
    res_valid = ladder.evaluate_tier_2_realistic_dbt(df=df_valid, suite=suite)
    assert res_valid["passed"] is True

    df_too_low = pd.DataFrame([{"order_id": "O2", "amount": 5.0}])
    res_too_low = ladder.evaluate_tier_2_realistic_dbt(df=df_too_low, suite=suite)
    assert res_too_low["passed"] is False
    assert "violates range [10.0, 1000.0]" in res_too_low["reason"]

    df_too_high = pd.DataFrame([{"order_id": "O3", "amount": 1500.0}])
    res_too_high = ladder.evaluate_tier_2_realistic_dbt(df=df_too_high, suite=suite)
    assert res_too_high["passed"] is False


def test_baseline_ladder_tier_2_accepted_values():
    ladder = BaselineLadderEvaluator()
    suite = AssertionSuite(name="status_domain_suite")
    suite.add(AcceptedValuesAssertion(
        column="status",
        values=["placed", "shipped", "completed", "return_pending", "returned"]
    ))

    df_valid = pd.DataFrame([{"order_id": "O1", "status": "completed"}])
    res_valid = ladder.evaluate_tier_2_realistic_dbt(df=df_valid, suite=suite)
    assert res_valid["passed"] is True

    df_invalid = pd.DataFrame([{"order_id": "O2", "status": "fraudulent_chargeback"}])
    res_invalid = ladder.evaluate_tier_2_realistic_dbt(df=df_invalid, suite=suite)
    assert res_invalid["passed"] is False
    assert "outside accepted values" in res_invalid["reason"]


def test_baseline_ladder_tier_2_relationships():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE customers (customer_id VARCHAR, name VARCHAR);")
    con.execute("INSERT INTO customers VALUES ('CUST_1', 'Alice'), ('CUST_2', 'Bob');")

    ladder = BaselineLadderEvaluator(conn=con)
    suite = AssertionSuite(name="fk_suite")
    suite.add(RelationshipsAssertion(
        from_column="customer_id",
        to_table="customers",
        to_column="customer_id"
    ))

    # Clean relationships
    df_valid = pd.DataFrame([{"order_id": "O1", "customer_id": "CUST_1"}])
    res_valid = ladder.evaluate_tier_2_realistic_dbt(df=df_valid, conn=con, suite=suite)
    assert res_valid["passed"] is True

    # Broken foreign key (orphan)
    df_orphan = pd.DataFrame([{"order_id": "O2", "customer_id": "CUST_UNKNOWN"}])
    res_orphan = ladder.evaluate_tier_2_realistic_dbt(df=df_orphan, conn=con, suite=suite)
    assert res_orphan["passed"] is False
    assert "orphan key(s)" in res_orphan["reason"]


def test_baseline_ladder_tier_2_singular_sql_test():
    con = duckdb.connect(":memory:")
    ladder = BaselineLadderEvaluator(conn=con)

    suite = AssertionSuite(name="singular_suite")
    # assert_positive_total_for_payments test from dbt-labs/jaffle_shop
    suite.add(SingularSqlAssertion(
        name="assert_positive_total_for_payments",
        sql="SELECT order_id, SUM(amount) AS total_amount FROM {{ model }} GROUP BY 1 HAVING NOT(SUM(amount) >= 0)"
    ))

    df_positive = pd.DataFrame([
        {"order_id": "O1", "amount": 100.0},
        {"order_id": "O1", "amount": -20.0},
    ])
    res_positive = ladder.evaluate_tier_2_realistic_dbt(df=df_positive, conn=con, suite=suite)
    assert res_positive["passed"] is True

    df_negative_total = pd.DataFrame([
        {"order_id": "O2", "amount": 20.0},
        {"order_id": "O2", "amount": -100.0},
    ])
    res_negative = ladder.evaluate_tier_2_realistic_dbt(df=df_negative_total, conn=con, suite=suite)
    assert res_negative["passed"] is False
    assert "assert_positive_total_for_payments" in res_negative["reason"]


def test_baseline_ladder_tier_2_sourced_jaffle_shop_yaml_suite():
    yaml_path = Path(__file__).resolve().parent.parent / "examples" / "assertions" / "realistic_dbt_suite.yaml"
    assert yaml_path.exists(), "realistic_dbt_suite.yaml should exist"

    suite = AssertionSuite.from_yaml_file(yaml_path)
    assert len(suite.assertions) == 7

    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE customers (customer_id VARCHAR);")
    con.execute("INSERT INTO customers VALUES ('CUST_100');")

    ladder = BaselineLadderEvaluator(conn=con, suite=suite)

    # Compliant dataframe matching all jaffle_shop tests
    df_clean = pd.DataFrame([{
        "order_id": "ORD_1",
        "customer_id": "CUST_100",
        "status": "placed",
        "amount": 250.0,
    }])
    res_clean = ladder.evaluate_tier_2_realistic_dbt(df=df_clean, conn=con, suite=suite)
    assert res_clean["passed"] is True
    assert res_clean["checks_count"] >= 5

    # Violates accepted_values (status)
    df_bad_status = pd.DataFrame([{
        "order_id": "ORD_2",
        "customer_id": "CUST_100",
        "status": "invalid_status",
        "amount": 250.0,
    }])
    assert ladder.evaluate_tier_2_realistic_dbt(df=df_bad_status, conn=con, suite=suite)["passed"] is False

    # Violates accepted_range (amount < 0)
    df_neg_amount = pd.DataFrame([{
        "order_id": "ORD_3",
        "customer_id": "CUST_100",
        "status": "completed",
        "amount": -50.0,
    }])
    assert ladder.evaluate_tier_2_realistic_dbt(df=df_neg_amount, conn=con, suite=suite)["passed"] is False


def test_baseline_ladder_tier_3_catches_missing_filter():
    comp = MetricCompiler.from_yaml_str(SAMPLE_CONTRACT_YAML)
    ladder = BaselineLadderEvaluator(contract=comp.definition)

    # Missing status = 'active' filter
    mutated_sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions GROUP BY 1"
    t3 = ladder.evaluate_tier_3_static_scos_ast(mutated_sql)
    assert t3["passed"] is False
    assert len(t3["violations"]) >= 1


def test_baseline_ladder_all_tiers_evaluation():
    comp = MetricCompiler.from_yaml_str(SAMPLE_CONTRACT_YAML)
    ladder = BaselineLadderEvaluator(contract=comp.definition)

    sql = comp.definition.sql
    df = pd.DataFrame([{"customer_id": "C1", "reporting_month": "2026-01-01", "net_revenue": 100.0}])

    res = ladder.evaluate_all_tiers(sql=sql, df=df)
    assert res["tier_0_syntax"] is True
    assert res["tier_1_minimal_structural"] is True
    assert res["tier_2_realistic_dbt"] is True
    assert res["tier_3_static_scos_ast"] is True

