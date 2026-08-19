from click.testing import CliRunner
from pathlib import Path
from semantic_reliability.cli import main

BASE_PATH = "examples/models/fct_net_revenue_baseline.sql"
CAND_PATH = "examples/models/fct_net_revenue_drifted.sql"
METRIC_PATH = "examples/metrics/net_revenue.yaml"


def test_cli_compile():
    runner = CliRunner()
    result = runner.invoke(main, ["compile", "--metric", METRIC_PATH, "--target-dialect", "snowflake"])
    assert result.exit_code == 0
    assert "Compiled Business Metric" in result.output


def test_cli_check_with_drift():
    runner = CliRunner()
    result = runner.invoke(main, ["check", "--base", BASE_PATH, "--candidate", CAND_PATH])
    assert result.exit_code == 0
    assert "Detected" in result.output
    assert "Filter conditions modified" in result.output or "SEMANTIC_LOGI" in result.output


def test_cli_check_with_fail_on_drift():
    runner = CliRunner()
    result = runner.invoke(main, ["check", "--base", BASE_PATH, "--candidate", CAND_PATH, "--fail-on-drift"])
    assert result.exit_code == 1


def test_cli_mutate(tmp_path):
    runner = CliRunner()
    out_dir = str(tmp_path / "mutations")
    result = runner.invoke(main, ["mutate", "--sql", BASE_PATH, "--output-dir", out_dir])
    assert result.exit_code == 0
    assert "Generating Chaos Mutations" in result.output
    assert Path(out_dir, "mutations_manifest.json").exists()


def test_cli_benchmark(tmp_path):
    runner = CliRunner()
    report_file = str(tmp_path / "report.md")
    result = runner.invoke(main, ["benchmark", "--sql", BASE_PATH, "--report", report_file])
    assert result.exit_code == 0
    assert "Catch Score" in result.output or "Mutation Score" in result.output
    assert Path(report_file).exists()


def test_cli_pr_comment(tmp_path):
    runner = CliRunner()
    comment_file = str(tmp_path / "comment.md")
    result = runner.invoke(main, ["pr-comment", "--base", BASE_PATH, "--candidate", CAND_PATH, "--output", comment_file])
    assert result.exit_code == 0
    assert Path(comment_file).exists()
    assert "Semantic Drift Alert" in Path(comment_file).read_text(encoding="utf-8")
