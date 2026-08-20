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
              - custom_unsupported_anomaly_test
              - dbt_expectations.expect_column_pair_values_to_be_in_set:
                  set: [1, 2]
    """
    f = tmp_path / "schema.yml"
    f.write_text(schema_yaml, encoding="utf-8")

    audit = DBTTestAdapter.parse_schema_yml_with_audit(f)
    assert audit.declared_tests_count == 6
    assert audit.supported_tests_count == 4
    assert audit.skipped_tests_count == 2
    assert any("custom_unsupported_anomaly_test" in s for s in audit.skipped_test_names)
    assert any("expect_column_pair_values_to_be_in_set" in s for s in audit.skipped_test_names)

