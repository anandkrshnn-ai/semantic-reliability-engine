import pytest
import pandas as pd
from semantic_reliability.harness.baseline_ladder import BaselineLadderEvaluator, BaselineTier
from semantic_reliability.compiler.compiler import MetricCompiler

SAMPLE_CONTRACT_YAML = """
metric: net_revenue
owner: finance
grain: customer_month
sql: "SELECT customer_id, DATE_TRUNC('month', transaction_date) AS reporting_month, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1, 2"
invariants:
  population:
    required_filters:
      - "status = 'active'"
  aggregation:
    negative_components:
      - "type = 'refund'"
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

def test_baseline_ladder_tier_2_catches_negative_revenue():
    comp = MetricCompiler.from_yaml_str(SAMPLE_CONTRACT_YAML)
    ladder = BaselineLadderEvaluator(contract=comp.definition)

    df_clean = pd.DataFrame([{"customer_id": "C1", "net_revenue": 100.0}])
    assert ladder.evaluate_tier_2_realistic_dbt(df_clean)["passed"] is True

    df_negative = pd.DataFrame([{"customer_id": "C1", "net_revenue": -50.0}])
    assert ladder.evaluate_tier_2_realistic_dbt(df_negative)["passed"] is False

def test_baseline_ladder_tier_3_catches_missing_filter():
    comp = MetricCompiler.from_yaml_str(SAMPLE_CONTRACT_YAML)
    ladder = BaselineLadderEvaluator(contract=comp.definition)

    # Missing status = 'active' filter
    mutated_sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions GROUP BY 1"
    t3 = ladder.evaluate_tier_3_static_scos_ast(mutated_sql)
    assert t3["passed"] is False
    assert len(t3["violations"]) >= 1
