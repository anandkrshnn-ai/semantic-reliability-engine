import pytest
from pathlib import Path
from click.testing import CliRunner
from semantic_reliability.cli import main

CORPUS_DIR = str(Path(__file__).resolve().parent.parent / "benchmark_corpus")


def test_cli_benchmark_corpus_split_holdout():
    runner = CliRunner()
    result = runner.invoke(main, ["benchmark-corpus", "--corpus", CORPUS_DIR, "--split", "holdout"])
    assert result.exit_code == 0
    assert "Frozen Holdout Track" in result.output
    assert "B2B Saas Arr" in result.output or "B2B" in result.output or "Saas" in result.output


def test_cli_benchmark_corpus_split_dev():
    runner = CliRunner()
    result = runner.invoke(main, ["benchmark-corpus", "--corpus", CORPUS_DIR, "--split", "dev"])
    assert result.exit_code == 0
    assert "Development Track" in result.output
    assert "Net Revenue" in result.output
