import pytest
from pathlib import Path
from semantic_reliability.adapters.dbt_adapter import DBTTestAdapter


def test_dbt_adapter_parse_schema(tmp_path):
    schema_yaml = """
    version: 2
    models:
      - name: fct_orders
        columns:
          - name: order_id
            tests:
              - unique
              - not_null
          - name: customer_id
            tests:
              - not_null
    """
    f = tmp_path / "schema.yml"
    f.write_text(schema_yaml, encoding="utf-8")

    suite = DBTTestAdapter.parse_schema_yml(f, model_name="fct_orders")
    assert len(suite.assertions) == 3
    assertion_names = [a.name for a in suite.assertions]
    assert any("not_null_order_id" in n for n in assertion_names)
    assert any("unique_order_id" in n for n in assertion_names)
    assert any("not_null_customer_id" in n for n in assertion_names)
