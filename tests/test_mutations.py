import pytest
import sqlglot
from semantic_reliability.mutations.engine import MutationEngine
from semantic_reliability.mutations.mutators import MutationType

BASE_SQL = """
SELECT
  customer_id,
  DATE_TRUNC('month', transaction_date) AS reporting_month,
  COALESCE(SUM(amount), 0) AS total_amount
FROM transactions
WHERE region = 'NA' AND amount > 100 AND status = 'active'
GROUP BY customer_id, DATE_TRUNC('month', transaction_date)
"""


def test_mutation_filter_drop():
    engine = MutationEngine(BASE_SQL)
    mut = engine.inject_filter_drop()
    assert mut is not None
    assert mut.mutation_type == MutationType.FILTER_DROP
    # Ensure mutated SQL parses cleanly
    parsed = sqlglot.parse_one(mut.mutated_sql)
    assert parsed is not None


def test_mutation_boundary_shift():
    engine = MutationEngine(BASE_SQL)
    mut = engine.inject_boundary_shift()
    assert mut is not None
    assert mut.mutation_type == MutationType.BOUNDARY_SHIFT
    assert ">=" in mut.mutated_sql


def test_mutation_aggregation_swap():
    engine = MutationEngine(BASE_SQL)
    mut = engine.inject_aggregation_swap()
    assert mut is not None
    assert mut.mutation_type == MutationType.AGGREGATION_SWAP
    assert "AVG(" in mut.mutated_sql.upper()


def test_mutation_coalesce_bypass():
    engine = MutationEngine(BASE_SQL)
    mut = engine.inject_coalesce_bypass()
    assert mut is not None
    assert mut.mutation_type == MutationType.COALESCE_BYPASS
    assert "COALESCE" not in mut.mutated_sql.upper()


def test_mutation_grain_drop():
    engine = MutationEngine(BASE_SQL)
    mut = engine.inject_grain_drop()
    assert mut is not None
    assert mut.mutation_type == MutationType.GRAIN_DROP


def test_generate_all_mutations():
    engine = MutationEngine(BASE_SQL)
    mutations = engine.generate_all_mutations()
    assert len(mutations) >= 4
    for m in mutations:
        assert sqlglot.parse_one(m.mutated_sql) is not None
