import pytest
from semantic_reliability.drift.normalizer import ASTNormalizer
from semantic_reliability.drift.detector import SemanticDriftDetector
import sqlglot


def test_commutative_and_predicates():
    sql_a = "SELECT * FROM t WHERE status = 'active' AND region = 'NA'"
    sql_b = "SELECT * FROM t WHERE region = 'NA' AND status = 'active'"

    drifts = SemanticDriftDetector.analyze(sql_a, sql_b)
    assert len(drifts) == 0, f"Expected 0 drifts for commutative AND, got {len(drifts)}"


def test_commutative_multi_conjuncts():
    sql_a = "SELECT * FROM t WHERE a = 1 AND b = 2 AND c = 3 AND d = 4"
    sql_b = "SELECT * FROM t WHERE d = 4 AND b = 2 AND a = 1 AND c = 3"

    drifts = SemanticDriftDetector.analyze(sql_a, sql_b)
    assert len(drifts) == 0


def test_commutative_or_predicates():
    sql_a = "SELECT * FROM t WHERE type = 'A' OR type = 'B'"
    sql_b = "SELECT * FROM t WHERE type = 'B' OR type = 'A'"

    drifts = SemanticDriftDetector.analyze(sql_a, sql_b)
    assert len(drifts) == 0


def test_redundant_parentheses():
    sql_a = "SELECT * FROM t WHERE (status = 'active') AND (region = 'NA')"
    sql_b = "SELECT * FROM t WHERE status = 'active' AND region = 'NA'"

    drifts = SemanticDriftDetector.analyze(sql_a, sql_b)
    assert len(drifts) == 0


def test_ast_normalizer_predicates_equality():
    node_a = sqlglot.parse_one("status = 'active' AND region = 'NA'")
    node_b = sqlglot.parse_one("region = 'NA' AND status = 'active'")

    assert ASTNormalizer.are_predicates_equivalent(node_a, node_b)
