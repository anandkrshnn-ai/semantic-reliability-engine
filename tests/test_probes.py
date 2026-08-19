import pytest
import duckdb
import pandas as pd
from click.testing import CliRunner

from semantic_reliability.compiler.schema import (
    MetricDefinition,
    MetricProbes,
    PopulationProbe,
    ImplicationProbe,
    NullDriftProbe,
)
from semantic_reliability.probes.engine import StatisticalProbeEngine
from semantic_reliability.probes.signals import SemanticProbeAlert
from semantic_reliability.cli import main


@pytest.fixture
def probe_db():
    con = duckdb.connect(":memory:")
    # 100 rows: 10 'active' with mrr > 0, 90 'churned' with mrr = 0, no nulls
    df = pd.DataFrame({
        "customer_id": [f"c_{i}" for i in range(100)],
        "status": ["active"] * 10 + ["churned"] * 90,
        "mrr_amount": [100.0] * 10 + [0.0] * 90,
    })
    con.register("transactions", df)
    return con


def test_population_probe_healthy(probe_db):
    metric_def = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT * FROM transactions",
        probes=MetricProbes(
            population=[
                PopulationProbe(
                    column="status",
                    target_value="active",
                    baseline_rate=0.10,  # 10% expected
                    tolerance=0.05,
                )
            ]
        )
    )

    engine = StatisticalProbeEngine(conn=probe_db, table_name="transactions")
    alerts = engine.run_all(metric_def)
    assert len(alerts) == 0  # No alert triggered, within tolerance


def test_population_probe_drift(probe_db):
    # Expect 80% active, but fixture only has 10% active -> triggers alert
    metric_def = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT * FROM transactions",
        probes=MetricProbes(
            population=[
                PopulationProbe(
                    column="status",
                    target_value="active",
                    baseline_rate=0.80,  # 80% expected
                    tolerance=0.05,
                )
            ]
        )
    )

    engine = StatisticalProbeEngine(conn=probe_db, table_name="transactions")
    alerts = engine.run_all(metric_def)

    assert len(alerts) == 1
    assert alerts[0].signal_type == "status_population_rate_shift"
    assert alerts[0].current == 0.10
    assert alerts[0].confidence == "high"


def test_implication_probe_decay():
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
                ImplicationProbe(
                    condition_column="status",
                    condition_value="active",
                    implication_column="mrr_amount",
                    implication_operator=">",
                    implication_value=0,
                    baseline_confidence=0.98,
                    tolerance_drop=0.05,
                )
            ]
        )
    )

    engine = StatisticalProbeEngine(conn=con, table_name="transactions")
    alerts = engine.run_all(metric_def)

    assert len(alerts) == 1
    assert "implies_mrr_amount_decay" in alerts[0].signal_type
    assert alerts[0].current == 0.50
    assert alerts[0].confidence == "high"


def test_null_drift_probe():
    con = duckdb.connect(":memory:")
    df = pd.DataFrame({
        "customer_id": [f"c_{i}" for i in range(100)],
        "status": ["active"] * 10 + [None] * 20 + ["churned"] * 70,
    })
    con.register("transactions", df)

    metric_def = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT * FROM transactions",
        probes=MetricProbes(
            null_drift=[
                NullDriftProbe(
                    column="status",
                    baseline_null_rate=0.0,
                    tolerance=0.05,
                )
            ]
        )
    )

    engine = StatisticalProbeEngine(conn=con, table_name="transactions")
    alerts = engine.run_all(metric_def)

    assert len(alerts) == 1
    assert alerts[0].signal_type == "status_null_rate_shift"
    assert alerts[0].current == 0.20


def test_cli_probe_command(tmp_path):
    contract_p = tmp_path / "probe_contract.yaml"
    contract_p.write_text("""
metric: net_revenue
owner: finance
grain: customer_month
sql: "SELECT * FROM transactions"
probes:
  population:
    - column: status
      target_value: 'active'
      baseline_rate: 0.80
      tolerance: 0.05
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
    assert "Semantic Probe" in result.output
    assert "status_population_rate_shift" in result.output
