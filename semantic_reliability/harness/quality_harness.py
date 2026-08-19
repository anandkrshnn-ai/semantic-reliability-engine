from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from semantic_reliability.mutations.engine import MutationEngine
from semantic_reliability.mutations.mutators import MutationResult, MutationType


class TestCheckResult(BaseModel):
    """Result of an individual data quality check."""
    check_name: str
    passed: bool
    details: str


class MutationEvaluation(BaseModel):
    """Evaluation of how existing data checks responded to an injected mutation."""
    mutation: MutationResult
    caught: bool
    catching_checks: List[str]
    failed_checks: List[str]
    check_results: Dict[str, str]
    blind_spot: bool


class MutationBenchmark(BaseModel):
    """Overall benchmark score measuring test suite robustness against semantic mutations."""
    total_mutations: int
    caught_mutations: int
    uncaught_mutations: int
    mutation_score_pct: float
    evaluations: List[MutationEvaluation]


class QualityHarness:
    """Simulates or executes test suites against mutated SQL models to calculate Mutation Score."""

    @staticmethod
    def simulate_standard_checks(mutated_sql: str, mutation_type: MutationType) -> Dict[str, str]:
        """
        Simulates standard industry data quality checks (e.g. dbt-expectations, Monte Carlo).
        Demonstrates the classic data observability blind spots.
        """
        results = {
            "Schema Validation": "PASS (Columns and data types valid)",
            "Null Rate Check": "PASS (Zero unexpected null values)",
            "Freshness SLA": "PASS (Data delivered within SLA window)",
            "Row Volume Anomaly": "PASS (Volume within normal bounds)",
            "Semantic Value Assertion": "FAIL (No semantic assertion configured)",
        }

        # Simulate which checks catch which mutation
        if mutation_type == MutationType.FILTER_DROP:
            # Volume checks might catch total filter drops if row count increases dramatically
            results["Row Volume Anomaly"] = "CAUGHT (Row count exceeded 3-sigma anomaly threshold)"
        elif mutation_type == MutationType.AGGREGATION_SWAP:
            # Value assertions catch drastic order-of-magnitude changes
            results["Semantic Value Assertion"] = "CAUGHT (Calculated aggregate deviated beyond expected range)"
        elif mutation_type == MutationType.BOUNDARY_SHIFT:
            # Boundary shifts (>= vs >) produce subtle 1-2% shifts that pass volume & null checks
            results["Row Volume Anomaly"] = "PASS (Volume within normal bounds)"
        elif mutation_type == MutationType.JOIN_PREDICATE_DROP:
            results["Row Volume Anomaly"] = "CAUGHT (Explosion in row count detected)"

        return results

    @classmethod
    def evaluate_model(
        cls,
        base_sql: str,
        dialect: Optional[str] = None,
        custom_test_runner: Optional[Any] = None,
    ) -> MutationBenchmark:
        """Run all mutations against base SQL and calculate mutation catch score."""
        mutator = MutationEngine(base_sql, dialect=dialect)
        mutations = mutator.generate_all_mutations()

        evaluations: List[MutationEvaluation] = []
        caught_count = 0

        for mut in mutations:
            if custom_test_runner:
                check_results = custom_test_runner(mut.mutated_sql, mut.mutation_type)
            else:
                check_results = cls.simulate_standard_checks(mut.mutated_sql, mut.mutation_type)

            catching = [k for k, v in check_results.items() if "CAUGHT" in v or "FAIL" in v and "No semantic" not in v]
            is_caught = len(catching) > 0

            if is_caught:
                caught_count += 1

            failed_checks = [k for k, v in check_results.items() if "PASS" in v]

            evaluations.append(MutationEvaluation(
                mutation=mut,
                caught=is_caught,
                catching_checks=catching,
                failed_checks=failed_checks,
                check_results=check_results,
                blind_spot=not is_caught,
            ))

        total = len(mutations)
        score_pct = (caught_count / total * 100.0) if total > 0 else 0.0

        return MutationBenchmark(
            total_mutations=total,
            caught_mutations=caught_count,
            uncaught_mutations=total - caught_count,
            mutation_score_pct=round(score_pct, 1),
            evaluations=evaluations,
        )
