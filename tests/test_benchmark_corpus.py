import pytest
from pathlib import Path
from click.testing import CliRunner
from semantic_reliability.cli import main

CORPUS_DIR = str(Path(__file__).resolve().parent.parent / "benchmark_corpus")


def test_cli_benchmark_corpus():
    runner = CliRunner()
    result = runner.invoke(main, ["benchmark-corpus", "--corpus", CORPUS_DIR])
    assert result.exit_code == 0
    assert "Benchmark Matrix" in result.output
    assert "Net Revenue" in result.output
    assert "Active" in result.output


def test_cli_benchmark_corpus_report(tmp_path):
    runner = CliRunner()
    report_file = str(tmp_path / "corpus_matrix.md")
    result = runner.invoke(main, ["benchmark-corpus", "--corpus", CORPUS_DIR, "--report", report_file])
    assert result.exit_code == 0
    assert Path(report_file).exists()
    content = Path(report_file).read_text(encoding="utf-8")
    assert "| net_revenue |" in content
    assert "| monthly_active_users |" in content
    assert "| customer_churn_rate |" in content
