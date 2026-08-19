import pytest
from semantic_reliability.compiler.compiler import MetricCompiler
from semantic_reliability.compiler.contracts import SemanticContractValidator

CONTRACT_YAML = """
metric: net_revenue
owner: finance
grain: customer_month
invariants:
  population:
    required_filters:
      - "status = 'active'"
      - "region = 'NA'"
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
  WHERE region = 'NA' AND status = 'active'
  GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
"""


def test_contract_validation_passes():
    compiler = MetricCompiler.from_yaml_str(CONTRACT_YAML)
    good_sql = compiler.get_ground_truth_sql()

    res = SemanticContractValidator.validate(good_sql, compiler.definition)
    assert res.passed is True
    assert len(res.violations) == 0


def test_contract_validation_catches_missing_filter():
    compiler = MetricCompiler.from_yaml_str(CONTRACT_YAML)
    bad_sql = """
    SELECT
      customer_id,
      DATE_TRUNC('month', transaction_date) AS reporting_month,
      SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
      SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
    FROM transactions
    WHERE region = 'NA'
    GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
    """
    res = SemanticContractValidator.validate(bad_sql, compiler.definition)
    assert res.passed is False
    assert any("status = 'active'" in v.invariant_rule for v in res.violations)


def test_contract_validation_catches_grain_drop():
    compiler = MetricCompiler.from_yaml_str(CONTRACT_YAML)
    bad_sql = """
    SELECT
      customer_id,
      SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) -
      SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue
    FROM transactions
    WHERE region = 'NA' AND status = 'active'
    GROUP BY customer_id
    """
    res = SemanticContractValidator.validate(bad_sql, compiler.definition)
    assert res.passed is False
    assert any("Reporting Grain" in v.invariant_category for v in res.violations)


def test_contract_validation_catches_missing_negative_component():
    compiler = MetricCompiler.from_yaml_str(CONTRACT_YAML)
    bad_sql = """
    SELECT
      customer_id,
      DATE_TRUNC('month', transaction_date) AS reporting_month,
      SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) AS net_revenue
    FROM transactions
    WHERE region = 'NA' AND status = 'active'
    GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
    """
    res = SemanticContractValidator.validate(bad_sql, compiler.definition)
    assert res.passed is False
    assert any("type = 'refund'" in v.invariant_rule for v in res.violations)
