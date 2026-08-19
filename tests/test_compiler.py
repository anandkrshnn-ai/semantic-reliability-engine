import pytest
from pathlib import Path
from semantic_reliability.compiler.compiler import MetricCompiler
from semantic_reliability.compiler.schema import MetricDefinition

SAMPLE_YAML = """
metric: test_net_sales
description: Gross sales minus discounts
owner: commerce
grain: daily
dialect: postgres
tags: [sales, core]
sql: |
  SELECT
    order_date,
    SUM(gross_amount) - SUM(discount_amount) AS net_sales
  FROM orders
  WHERE order_status = 'completed' AND is_test = false
  GROUP BY order_date
"""


def test_compiler_from_yaml_str():
    compiler = MetricCompiler.from_yaml_str(SAMPLE_YAML)
    assert compiler.definition.metric == "test_net_sales"
    assert compiler.definition.owner == "commerce"
    assert compiler.definition.grain == "daily"
    assert "orders" in compiler.get_tables()
    assert len(compiler.get_aggregation_nodes()) == 2
    assert compiler.get_where_ast() is not None


def test_compiler_from_dict():
    data = {
        "metric": "mrr",
        "owner": "finance",
        "grain": "monthly",
        "sql": "SELECT SUM(amount) AS mrr FROM subs WHERE active = true",
    }
    compiler = MetricCompiler.from_dict(data)
    assert compiler.definition.metric == "mrr"
    assert compiler.get_ground_truth_sql() is not None


def test_compiler_transpile_snowflake():
    compiler = MetricCompiler.from_yaml_str(SAMPLE_YAML)
    sf_sql = compiler.get_ground_truth_sql(target_dialect="snowflake")
    assert "net_sales" in sf_sql.lower()


def test_compiler_invalid_sql():
    invalid_yaml = """
metric: bad_metric
owner: dev
grain: raw
sql: "SELECT FROM WHERE"
"""
    with pytest.raises(ValueError, match="Failed to parse ground-truth SQL"):
        MetricCompiler.from_yaml_str(invalid_yaml)
