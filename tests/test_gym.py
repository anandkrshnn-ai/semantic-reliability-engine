import json
import pytest
from pathlib import Path
from click.testing import CliRunner

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.gym.generator import SemanticGymGenerator
from semantic_reliability.gym.difficulty import calibrate_difficulty, MutationDifficulty
from semantic_reliability.gym.export import export_gym_dataset
from semantic_reliability.cli import main


@pytest.fixture
def sample_metric():
    return MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY customer_id",
        dialect="duckdb",
        description="Total net revenue from active customer accounts",
    )


def test_gym_dpo_pair_generation(sample_metric):
    gen = SemanticGymGenerator(sample_metric)
    pairs = gen.generate_dpo_pairs()

    assert len(pairs) > 0
    first = pairs[0]
    assert first.chosen == sample_metric.sql.strip()
    assert first.rejected != sample_metric.sql.strip()
    assert first.metric_id == "net_revenue"
    assert first.difficulty in ("EASY", "MEDIUM", "HARD", "EXPERT")

    dpo_dict = first.to_jsonl_dict()
    assert "prompt" in dpo_dict
    assert "chosen" in dpo_dict
    assert "rejected" in dpo_dict
    assert dpo_dict["metadata"]["metric_id"] == "net_revenue"


def test_gym_rlhf_item_generation(sample_metric):
    gen = SemanticGymGenerator(sample_metric)
    items = gen.generate_rlhf_items()

    assert len(items) > 0
    first = items[0]
    assert len(first.completions) == 2
    assert first.completions[0]["reward"] == 1.0
    assert first.completions[1]["reward"] == 0.0


def test_gym_sft_instruction_generation(sample_metric):
    gen = SemanticGymGenerator(sample_metric)
    instructions = gen.generate_sft_instructions()

    assert len(instructions) > 0
    first = instructions[0]
    assert "net_revenue" in first.instruction
    assert "business definition" in first.semantic_rationale
    assert first.output == sample_metric.sql.strip()


def test_gym_difficulty_calibration():
    assert calibrate_difficulty("AGGREGATION_SWAP") == MutationDifficulty.EASY
    assert calibrate_difficulty("FILTER_DROP") == MutationDifficulty.MEDIUM
    assert calibrate_difficulty("BOUNDARY_SHIFT") == MutationDifficulty.HARD
    assert calibrate_difficulty("MATH_OPERATOR_INVERT") == MutationDifficulty.EXPERT


def test_cli_export_gym_command(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    metric_file = corpus_dir / "net_revenue.yaml"
    metric_file.write_text("""
metric: net_revenue
owner: finance
grain: customer_month
sql: "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY customer_id"
dialect: duckdb
""", encoding="utf-8")

    out_file = tmp_path / "dpo_dataset.jsonl"
    runner = CliRunner()
    result = runner.invoke(main, [
        "export-gym",
        "--corpus", str(corpus_dir),
        "--format", "dpo",
        "--output", str(out_file)
    ])

    assert result.exit_code == 0
    assert "Exporting Semantic Gym Training Dataset" in result.output
    assert out_file.exists()

    lines = out_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) > 0
    first_record = json.loads(lines[0])
    assert "prompt" in first_record
    assert "chosen" in first_record
    assert "rejected" in first_record
