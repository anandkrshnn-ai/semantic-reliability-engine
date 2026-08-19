import json
from pathlib import Path
import pytest
from click.testing import CliRunner

from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant
from semantic_reliability.adapters.bigquery import BigQueryDryRunAdapter, BigQueryPricingPolicy
from semantic_reliability.adapters.dbt_integration import DbtManifestResolver, DbtSreChecker, NodeResolutionStatus
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


def test_bigquery_adapter_default_pricing(sample_metric_def):
    adapter = BigQueryDryRunAdapter()
    sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` WHERE status = 'active' GROUP BY customer_id"
    # Exactly 1 TiB (1024^4 bytes)
    res = adapter.evaluate(sql, sample_metric_def, dialect="bigquery", mock_bytes_processed=1024**4)

    assert res["decision"] == "ALLOW"
    assert res["contract_compliant"] is True
    assert res["bytes_processed"] == 1024**4
    assert res["cost_estimate"]["price_per_tib_usd"] == 6.25  # $6.25/TiB default
    assert res["cost_estimate"]["estimated_gross_cost_usd"] == 6.25
    assert "local_ast_latency_ms" in res
    assert "dry_run_api_latency_ms" in res


def test_bigquery_adapter_custom_pricing_and_free_tier(sample_metric_def):
    policy = BigQueryPricingPolicy(
        price_per_tib_usd=5.0,
        monthly_free_tib=1.0,
    )
    adapter = BigQueryDryRunAdapter(policy=policy)
    sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` WHERE status = 'active' GROUP BY customer_id"
    # 3 TiB with free tier applied
    res = adapter.evaluate(
        sql,
        sample_metric_def,
        dialect="bigquery",
        mock_bytes_processed=3 * (1024**4),
        apply_free_tier=True,
    )

    assert res["cost_estimate"]["price_per_tib_usd"] == 5.0
    assert res["cost_estimate"]["estimated_gross_cost_usd"] == 15.0  # 3 * $5
    assert res["cost_estimate"]["estimated_billable_cost_usd"] == 10.0  # (3 - 1) * $5


def test_bigquery_byte_budget_enforcement(sample_metric_def):
    policy = BigQueryPricingPolicy(maximum_bytes_billed=100 * 1024 * 1024)  # 100 MB budget
    adapter = BigQueryDryRunAdapter(policy=policy)
    sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` WHERE status = 'active' GROUP BY customer_id"
    # 500 MB (exceeds budget)
    res = adapter.evaluate(sql, sample_metric_def, dialect="bigquery", mock_bytes_processed=500 * 1024 * 1024)

    assert res["decision"] == "DENY"
    assert res["execution_mode"] == "budget_exceeded"
    assert "Byte budget exceeded" in res["bq_error"]


def test_bigquery_require_project_id_policy(sample_metric_def):
    policy = BigQueryPricingPolicy(require_project_id=True)
    adapter = BigQueryDryRunAdapter(project_id=None, policy=policy)
    sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM `my_proj.dataset.transactions` WHERE status = 'active' GROUP BY customer_id"
    res = adapter.evaluate(sql, sample_metric_def)

    assert res["decision"] == "DENY"
    assert res["execution_mode"] == "policy_denied"
    assert "project_id is required" in res["bq_error"]


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
            },
            "model.my_project.fct_uncompiled": {
                "name": "fct_uncompiled",
                "resource_type": "model",
                "raw_code": "SELECT * FROM {{ ref('raw_transactions') }}",
                "compiled_code": None,
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
    assert res_clean["compiled_sql_available"] is True
    assert res_clean["decision"] == "ALLOW"

    # Drifted model
    res_drifted = checker.check("fct_drifted_revenue", contract_yaml)
    assert len(res_drifted["drift_alerts"]) > 0
    assert res_drifted["decision"] == "DENY"

    # Uncompiled model failure
    with pytest.raises(ValueError) as exc:
        checker.check("fct_uncompiled", contract_yaml, require_compiled=True)
    assert "has no compiled SQL" in str(exc.value)


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
