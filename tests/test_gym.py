import json
import pytest
import pandas as pd
from pathlib import Path
from click.testing import CliRunner

from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant
from semantic_reliability.gym.models import GymEvidenceItem, CandidateRejectionStats
from semantic_reliability.gym.generator import SemanticGymGenerator
from semantic_reliability.gym.difficulty import calibrate_difficulty
from semantic_reliability.gym.split import assign_dataset_split
from semantic_reliability.gym.export import export_gym_dataset
from semantic_reliability.gym.formatters.dpo import format_to_dpo
from semantic_reliability.gym.formatters.sft import format_to_sft
from semantic_reliability.gym.formatters.rlhf import format_to_rlhf
from semantic_reliability.cli import main


@pytest.fixture
def gym_test_fixture(tmp_path):
    csv_p = tmp_path / "transactions.csv"
    df = pd.DataFrame({
        "customer_id": [f"c_{i}" for i in range(100)],
        "status": ["active"] * 50 + ["churned"] * 50,
        "amount": [10.0] * 50 + [0.0] * 50,
    })
    df.to_csv(csv_p, index=False)

    metric_def = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY customer_id",
        dialect="duckdb",
        description="Total net revenue from active customer accounts",
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"])
        )
    )

    return metric_def, csv_p


def test_gym_evidence_pair_generation(gym_test_fixture):
    metric_def, csv_p = gym_test_fixture
    gen = SemanticGymGenerator(metric_def=metric_def, fixture_path=csv_p, table_name="transactions")
    stats = CandidateRejectionStats()
    pairs = gen.generate_evidence_pairs(stats=stats)

    assert len(pairs) > 0
    assert stats.candidates_generated > 0
    assert stats.accepted_pairs == len(pairs)

    first = pairs[0]
    assert first.chosen_sql.strip() == metric_def.sql.strip()
    assert first.rejected_sql.strip() != metric_def.sql.strip()
    assert first.chosen_evidence.execution_success is True
    assert first.chosen_evidence.contract_compliant is True
    assert len(first.evidence_hash) > 0
    assert first.difficulty in ("easy", "medium", "hard", "expert")
    assert first.split in ("train", "val", "holdout")


def test_gym_formatters(gym_test_fixture):
    metric_def, csv_p = gym_test_fixture
    gen = SemanticGymGenerator(metric_def=metric_def, fixture_path=csv_p, table_name="transactions")
    pairs = gen.generate_evidence_pairs()
    item = pairs[0]

    dpo = format_to_dpo(item)
    assert "prompt" in dpo and "chosen" in dpo and "rejected" in dpo
    assert dpo["metadata"]["metric_id"] == "net_revenue"
    assert "evidence_hash" in dpo["metadata"]

    sft = format_to_sft(item)
    assert "instruction" in sft and "output" in sft and "semantic_rationale" in sft

    rlhf = format_to_rlhf(item)
    assert len(rlhf["completions"]) == 2
    assert rlhf["completions"][0]["reward"] == 1.0
    assert rlhf["completions"][1]["reward"] == 0.0


def test_structured_splitting():
    assert assign_dataset_split("net_revenue", "finance", "FILTER_DROP") == "train"
    assert assign_dataset_split("net_revenue", "finance", "BOUNDARY_SHIFT") == "val"
    assert assign_dataset_split("net_revenue", "finance", "GRAIN_DROP") == "holdout"
    assert assign_dataset_split("icu_admission", "healthcare", "FILTER_DROP") == "holdout"


def test_difficulty_calibration():
    assert calibrate_difficulty("MATH_OPERATOR_INVERT") == "expert"
    assert calibrate_difficulty("JOIN_PREDICATE_DROP") == "expert"
    assert calibrate_difficulty("BOUNDARY_SHIFT") == "hard"
    assert calibrate_difficulty("FILTER_DROP", variance_pct=2.0) == "hard"  # subtle variance
    assert calibrate_difficulty("FILTER_DROP", variance_pct=50.0) == "medium"
    assert calibrate_difficulty("AGGREGATION_SWAP") == "easy"


def test_cli_export_and_inspect_gym(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    metric_file = corpus_dir / "net_revenue.yaml"
    metric_file.write_text("""
metric: net_revenue
owner: finance
grain: customer_month
sql: "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY customer_id"
dialect: duckdb
invariants:
  population:
    required_filters:
      - "status = 'active'"
""", encoding="utf-8")

    csv_p = corpus_dir / "net_revenue.csv"
    df = pd.DataFrame({"customer_id": ["c1", "c2"], "status": ["active", "churned"], "amount": [10.0, 0.0]})
    df.to_csv(csv_p, index=False)

    out_file = tmp_path / "exported_dpo.jsonl"
    runner = CliRunner()

    # Test export-gym command
    res_export = runner.invoke(main, [
        "export-gym",
        "--corpus", str(corpus_dir),
        "--format", "dpo",
        "--split", "all",
        "--output", str(out_file)
    ])

    assert res_export.exit_code == 0
    assert "Generation Summary" in res_export.output
    assert "Accepted Preference Pairs" in res_export.output
    assert out_file.exists()

    # Test inspect-gym command
    res_inspect = runner.invoke(main, [
        "inspect-gym",
        "--dataset", str(out_file),
        "--show-evidence",
        "--limit", "1"
    ])

    assert res_inspect.exit_code == 0
    assert "Inspecting Semantic Gym Dataset" in res_inspect.output
    assert "Chosen SQL (Compliant)" in res_inspect.output
    assert "Rejected SQL (Mutated)" in res_inspect.output
    assert "Semantic Evidence" in res_inspect.output
