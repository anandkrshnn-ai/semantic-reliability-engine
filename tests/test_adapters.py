import json
from pathlib import Path
import pytest
from click.testing import CliRunner

from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant
from semantic_reliability.adapters.bigquery import BigQueryDryRunAdapter
from semantic_reliability.adapters.dbt_integration import DbtManifestResolver, DbtSreChecker
from semantic_reliability.cli import main


@pytest.fixture
def sample_metric_def():
    return MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` WHERE status = 'active' GROUP BY customer_id",
        dialect="bigquery",
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"])
        )
    )


def test_bigquery_adapter_compliant(sample_metric_def):
    adapter = BigQueryDryRunAdapter()
    sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` WHERE status = 'active' GROUP BY customer_id"
    res = adapter.evaluate(sql, sample_metric_def, dialect="bigquery", mock_bytes_processed=1024**4)  # 1 TB

    assert res["decision"] == "ALLOW"
    assert res["contract_compliant"] is True
    assert res["bytes_processed"] == 1024**4
    assert res["estimated_cost"] == 5.0  # $5/TB


def test_bigquery_adapter_violation(sample_metric_def):
    adapter = BigQueryDryRunAdapter()
    # Missing required filter status = 'active'
    sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` GROUP BY customer_id"
    res = adapter.evaluate(sql, sample_metric_def, dialect="bigquery", mock_bytes_processed=500000)

    assert res["decision"] == "REQUIRE_REVIEW"
    assert res["contract_compliant"] is False
    assert len(res["violations"]) > 0


def test_dbt_manifest_resolver_and_checker(tmp_path):
    manifest_data = {
        "metadata": {"adapter_type": "bigquery"},
        "nodes": {
            "model.my_project.fct_net_revenue": {
                "name": "fct_net_revenue",
                "resource_type": "model",
                "compiled_code": "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` WHERE status = 'active' GROUP BY customer_id",
                "config": {"adapter_type": "bigquery"}
            },
            "model.my_project.fct_drifted_revenue": {
                "name": "fct_drifted_revenue",
                "resource_type": "model",
                "compiled_code": "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` GROUP BY customer_id",
                "config": {"adapter_type": "bigquery"}
            }
        }
    }

    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    contract_yaml = tmp_path / "contract.yaml"
    contract_yaml.write_text("""
metric: net_revenue
owner: finance
grain: customer_month
sql: "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` WHERE status = 'active' GROUP BY customer_id"
dialect: bigquery
invariants:
  population:
    required_filters:
      - "status = 'active'"
""", encoding="utf-8")

    checker = DbtSreChecker(manifest_file)

    # Clean model
    res_clean = checker.check("fct_net_revenue", contract_yaml)
    assert res_clean["has_critical_drift"] is False
    assert len(res_clean["drift_alerts"]) == 0

    # Drifted model
    res_drifted = checker.check("fct_drifted_revenue", contract_yaml)
    assert len(res_drifted["drift_alerts"]) > 0


def test_cli_dbt_check(tmp_path):
    manifest_data = {
        "metadata": {"adapter_type": "bigquery"},
        "nodes": {
            "model.my_project.fct_net_revenue": {
                "name": "fct_net_revenue",
                "resource_type": "model",
                "compiled_code": "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` WHERE status = 'active' GROUP BY customer_id",
            }
        }
    }

    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    contract_yaml = tmp_path / "contract.yaml"
    contract_yaml.write_text("""
metric: net_revenue
owner: finance
grain: customer_month
sql: "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` WHERE status = 'active' GROUP BY customer_id"
dialect: bigquery
""", encoding="utf-8")

    sarif_out = tmp_path / "drift.sarif"
    runner = CliRunner()

    res = runner.invoke(main, [
        "dbt-check",
        "--manifest", str(manifest_file),
        "--model", "fct_net_revenue",
        "--contract", str(contract_yaml),
        "--fail-on", "critical",
        "--output-sarif", str(sarif_out)
    ])

    assert res.exit_code == 0
    assert "semantically compliant" in res.output
    assert sarif_out.exists()
