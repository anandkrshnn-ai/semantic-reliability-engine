"""Unit tests for the mechanical provenance verification engine."""

import pytest
from pathlib import Path
from semantic_reliability.evaluation.provenance_auditor import ProvenanceAuditor, ProvenanceClaim


def test_extract_provenance_claims(tmp_path):
    schema_yaml = """
    # Provenance:
    #   Repository: https://github.com/dbt-labs/jaffle_shop
    #   Organization: dbt Labs
    #   Reference: models/staging/schema.yml

    version: 2
    models:
      - name: stg_orders
        columns:
          - name: status
            tests:
              - accepted_values:
                  values: ['placed', 'shipped', 'completed', 'return_pending', 'returned']
    """
    f = tmp_path / "schema.yml"
    f.write_text(schema_yaml, encoding="utf-8")

    claims = ProvenanceAuditor.extract_claims_from_yaml(f)
    assert len(claims) == 1
    assert claims[0].repository == "https://github.com/dbt-labs/jaffle_shop"
    assert claims[0].organization == "dbt Labs"
    assert claims[0].reference_path == "models/staging/schema.yml"
    assert "status" in claims[0].claimed_symbols
    assert "shipped" in claims[0].claimed_symbols


def test_provenance_auditor_detects_non_existent_file(tmp_path):
    claim = ProvenanceClaim(
        source_file="test.yml",
        repository="https://github.com/dbt-labs/jaffle_shop",
        reference_path="models/non_existent_schema_file.yml",
        claimed_symbols=["status"],
    )
    result = ProvenanceAuditor.verify_claim(claim, cache_dir=tmp_path)
    assert result.passed is False
    assert result.file_exists is False
    assert "does not exist" in result.reason


def test_provenance_auditor_detects_fabricated_symbols(tmp_path):
    # jaffle_shop does not have a 'department' column or 'starter/pro/enterprise' plans in stg_orders
    fake_repo_dir = tmp_path / "fake_repo"
    fake_repo_dir.mkdir(parents=True, exist_ok=True)
    (fake_repo_dir / ".git").mkdir()
    (fake_repo_dir / "schema.yml").write_text("models:\n  - name: orders\n    columns:\n      - name: order_id\n", encoding="utf-8")

    claim = ProvenanceClaim(
        source_file="test.yml",
        repository="https://github.com/dbt-labs/fake_repo",
        reference_path="schema.yml",
        claimed_symbols=["order_id", "department", "starter"],
    )
    result = ProvenanceAuditor.verify_claim(claim, cache_dir=tmp_path)
    assert result.passed is False
    assert "department" in result.missing_symbols
    assert "starter" in result.missing_symbols
    assert "order_id" in result.verified_symbols
