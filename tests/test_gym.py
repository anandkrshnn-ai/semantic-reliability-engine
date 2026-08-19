import json
import pytest
import pandas as pd
from pathlib import Path
from click.testing import CliRunner

from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant
from semantic_reliability.gym.models import (
    GymExample,
    RejectionReason,
    SPLIT_RULES,
    assign_split,
    assign_difficulty,
    compute_evidence_hash,
)
from semantic_reliability.gym.generator import GymGenerator
from semantic_reliability.gym.formatters import get_formatter, DPOFormatter, SFTFormatter, RLHFFormatter
from semantic_reliability.gym.inspector import inspect_dataset
from semantic_reliability.cli import main


@pytest.fixture
def test_corpus(tmp_path):
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
    return corpus_dir, csv_p


def test_gym_generator_end_to_end(test_corpus):
    corpus_dir, _ = test_corpus
    generator = GymGenerator(corpus_dir=corpus_dir)
    examples = generator.generate(target_split="all")

    assert len(examples) > 0
    first = examples[0]
    assert first.chosen_sql.startswith("SELECT")
    assert first.rejected_sql.startswith("SELECT")
    assert first.chosen_evidence["execution"] is True
    assert first.chosen_evidence["contract_passed"] is True
    assert first.evidence_hash != ""
    assert first.difficulty in ("easy", "medium", "hard")


def test_gym_formatters(test_corpus):
    corpus_dir, _ = test_corpus
    generator = GymGenerator(corpus_dir=corpus_dir)
    examples = generator.generate(target_split="all")
    ex = examples[0]

    dpo = get_formatter("dpo").format(ex)
    assert "prompt" in dpo and "chosen" in dpo and "rejected" in dpo
    assert dpo["metadata"]["contract_id"] == "net_revenue"

    sft = get_formatter("sft").format(ex)
    assert "prompt" in sft and "completion" in sft and "semantic_rationale" in sft

    rlhf = get_formatter("rlhf").format(ex)
    assert len(rlhf["completions"]) == 2
    assert rlhf["completions"][0]["reward"] == 1.0
    assert rlhf["completions"][1]["reward"] == 0.0


def test_gym_split_and_difficulty():
    split_res = assign_split("net_revenue", "finance")
    assert split_res in ("train", "validation", "holdout")

    diff, reasons = assign_difficulty("FILTER_DROP", None)
    assert diff == "easy"
    assert "direct_ast_mutation" in reasons

    diff_math, _ = assign_difficulty("MATH_OPERATOR_INVERT", None)
    assert diff_math == "hard"

    # Test full 64-character SHA-256 evidence hash
    ev_hash = compute_evidence_hash({"test": "data", "num": 123})
    assert len(ev_hash) == 64


def test_cli_export_and_audit(test_corpus, tmp_path):
    corpus_dir, _ = test_corpus
    out_file = tmp_path / "train_dpo.jsonl"
    audit_json = tmp_path / "audit_report.json"
    runner = CliRunner()

    res_export = runner.invoke(main, [
        "export-gym",
        "--corpus", str(corpus_dir),
        "--split", "all",
        "--format", "dpo",
        "--output", str(out_file)
    ])

    assert res_export.exit_code == 0
    assert "Exported" in res_export.output
    assert out_file.exists()

    res_audit = runner.invoke(main, [
        "audit-gym",
        "--dataset", str(out_file),
        "--output", str(audit_json)
    ])

    assert res_audit.exit_code == 0
    assert "Audit Status: PASSED" in res_audit.output
    assert "Mutation Distribution" in res_audit.output
    assert "Difficulty Distribution" in res_audit.output
    assert audit_json.exists()

