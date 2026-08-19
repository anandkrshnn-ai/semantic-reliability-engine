import pytest
import duckdb
import pandas as pd
from click.testing import CliRunner

from semantic_reliability.compiler.schema import (
    MetricDefinition,
    MetricProbes,
    PopulationStabilityProbe,
    SemanticImplicationProbe,
)
from semantic_reliability.probes.engine import StatisticalProbeEngine
from semantic_reliability.cli import main


@pytest.fixture
def probe_db():
    con = duckdb.connect(":memory:")
    # Create sample customer transactions table
    # 100 rows: 10 'active' with mrr > 0, 90 'churned' with mrr = 0
    df = pd.DataFrame({
        "customer_id": [f"c_{i}" for i in range(100)],
        "status": ["active"] * 10 + ["churned"] * 90,
        "mrr_amount": [100.0] * 10 + [0.0] * 90,
    })
    con.register("transactions", df)
    return con


def test_population_stability_healthy(probe_db):
    metric_def = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT * FROM transactions",
        probes=MetricProbes(
            population_stability=[
                PopulationStabilityProbe(
                    column="status",
                    target_value="active",
                    baseline_rate=0.10,  # 10% expected
                    threshold_std_dev=3.0,
                )
            ]
        )
    )

    engine = StatisticalProbeEngine(conn=probe_db, table_name="transactions")
    signals = engine.run_all(metric_def)

    assert len(signals) == 1
    assert signals[0].status == "HEALTHY"
    assert signals[0].current_value == 0.10


def test_population_stability_critical_drift(probe_db):
    # Expect 80% active, but fixture only has 10% active -> huge Z-score
    metric_def = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT * FROM transactions",
        probes=MetricProbes(
            population_stability=[
                PopulationStabilityProbe(
                    column="status",
                    target_value="active",
                    baseline_rate=0.80,  # 80% expected
                    threshold_std_dev=3.0,
                )
            ]
        )
    )

    engine = StatisticalProbeEngine(conn=probe_db, table_name="transactions")
    signals = engine.run_all(metric_def)

    assert len(signals) == 1
    assert signals[0].status == "CRITICAL"
    assert signals[0].deviation > 5.0


def test_semantic_implication_healthy(probe_db):
    # In fixture: 100% of 'active' users have mrr_amount > 0
    metric_def = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT * FROM transactions",
        probes=MetricProbes(
            implications=[
                SemanticImplicationProbe(
                    condition_column="status",
                    condition_value="active",
                    implication_column="mrr_amount",
                    implication_operator=">",
                    implication_value=0,
                    baseline_confidence=0.95,
                    threshold_drop=0.10,
                )
            ]
        )
    )

    engine = StatisticalProbeEngine(conn=probe_db, table_name="transactions")
    signals = engine.run_all(metric_def)

    assert len(signals) == 1
    assert signals[0].status == "HEALTHY"
    assert signals[0].current_value == 1.0


def test_semantic_implication_break():
    # Construct drifted database where 5 of 10 'active' users have mrr_amount = 0 (Free Trial dilution)
    con = duckdb.connect(":memory:")
    df = pd.DataFrame({
        "customer_id": [f"c_{i}" for i in range(100)],
        "status": ["active"] * 10 + ["churned"] * 90,
        "mrr_amount": [100.0] * 5 + [0.0] * 5 + [0.0] * 90,
    })
    con.register("transactions", df)

    metric_def = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT * FROM transactions",
        probes=MetricProbes(
            implications=[
                SemanticImplicationProbe(
                    condition_column="status",
                    condition_value="active",
                    implication_column="mrr_amount",
                    implication_operator=">",
                    implication_value=0,
                    baseline_confidence=0.98,
                    threshold_drop=0.05,
                )
            ]
        )
    )

    engine = StatisticalProbeEngine(conn=con, table_name="transactions")
    signals = engine.run_all(metric_def)

    assert len(signals) == 1
    assert signals[0].status == "CRITICAL"
    assert signals[0].current_value == 0.50  # Only 50% paid
    assert "Semantic Implication" in signals[0].probe_type


def test_cli_probe_command(tmp_path):
    contract_p = tmp_path / "probe_contract.yaml"
    contract_p.write_text("""
metric: net_revenue
owner: finance
grain: customer_month
sql: "SELECT * FROM transactions"
probes:
  population_stability:
    - column: status
      target_value: 'active'
      baseline_rate: 0.80
      threshold_std_dev: 2.0
""", encoding="utf-8")

    csv_p = tmp_path / "transactions.csv"
    df = pd.DataFrame({"status": ["active"] * 10 + ["churned"] * 90})
    df.to_csv(csv_p, index=False)

    runner = CliRunner()
    result = runner.invoke(main, [
        "probe",
        "--contract", str(contract_p),
        "--fixture", str(csv_p),
        "--table-name", "transactions"
    ])

    assert result.exit_code == 0
    assert "Scanning Semantic Reality" in result.output
    assert "Population Stability" in result.output
