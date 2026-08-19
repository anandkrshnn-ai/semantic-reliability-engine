import json
from pathlib import Path
import pytest
import jsonschema


def test_scos_schema_validity():
    schema_path = Path("spec/scos-v1.schema.json")
    assert schema_path.exists()
    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))

    # Verify schema itself is valid Draft 2020-12
    jsonschema.Draft202012Validator.check_schema(schema_data)


def test_scos_schema_validation_on_sample_contract():
    schema_path = Path("spec/scos-v1.schema.json")
    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))

    valid_contract = {
        "scos_version": "1.0.0",
        "id": "urn:scos:finance:net_revenue",
        "metric": "net_revenue",
        "version": "1.0.0",
        "description": "Calculates net recurring revenue from active subscriptions.",
        "owner": "finance@company.com",
        "domain": "finance",
        "grain": "customer_month",
        "dialect": "bigquery",
        "sql": "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1",
        "invariants": {
            "population": {
                "required_filters": ["status = 'active'"],
                "forbidden_filters": ["status = 'cancelled'"]
            },
            "deduction": {
                "required_subtractions": ["discount"]
            }
        },
        "probes": {
            "population": [
                {
                    "predicate": "status = 'active'",
                    "min_rate": 0.05,
                    "max_rate": 0.30
                }
            ]
        }
    }

    # Should validate without raising ValidationError
    jsonschema.validate(instance=valid_contract, schema=schema_data)


def test_scos_schema_rejects_invalid_contract():
    schema_path = Path("spec/scos-v1.schema.json")
    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))

    invalid_contract = {
        "scos_version": "1.0.0",
        # Missing required 'metric', 'owner', 'grain', 'sql'
        "description": "Incomplete metric"
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_contract, schema=schema_data)
