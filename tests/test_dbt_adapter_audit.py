import pytest
from semantic_reliability.adapters.dbt_adapter import DBTTestAdapter


def test_dbt_adapter_audit_skipped_tests(tmp_path):
    schema_yaml = """
    version: 2
    models:
      - name: fct_transactions
        columns:
          - name: id
            tests:
              - unique
              - not_null
              - accepted_values:
                  values: ['A', 'B']
              - relationships:
                  to: ref('dim_users')
                  field: id
    """
    f = tmp_path / "schema.yml"
    f.write_text(schema_yaml, encoding="utf-8")

    audit = DBTTestAdapter.parse_schema_yml_with_audit(f)
    assert audit.declared_tests_count == 4
    assert audit.supported_tests_count == 2
    assert audit.skipped_tests_count == 2
    assert any("accepted_values" in s for s in audit.skipped_test_names)
    assert any("relationships" in s for s in audit.skipped_test_names)
