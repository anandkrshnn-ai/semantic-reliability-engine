"""
Phase 8.2 Replay Worker
Consumes firewall audit logs and evaluates mutation adequacy offline.
"""
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

import yaml
import pandas as pd
from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.mutations.engine import MutationEngine
from semantic_reliability.harness.duckdb_runner import DuckDBFixtureRunner, MutationClassification
from semantic_reliability.assertions.registry import AssertionSuite
from semantic_reliability.assertions.semantic import MetricValueAssertion, RequiredPopulationAssertion

logger = logging.getLogger("sre.replay")


class BlindSpot(BaseModel):
    mutation_id: str
    mutation_type: str
    description: str
    empirical_variance_pct: float
    summary: str


class ReplayResult(BaseModel):
    trace_id: str
    metric_id: str
    original_sql: str
    catch_score: float
    total_valid_defects: int
    undetected_defects: int
    blind_spots: List[BlindSpot] = Field(default_factory=list)
    contract_underspecified: bool


class SnapshotProvider:
    """Interface for retrieving fixture data snapshots for replayed metrics."""

    def get_snapshot(self, metric_id: str) -> Dict[str, Any]:
        raise NotImplementedError


class LocalFixtureSnapshotProvider(SnapshotProvider):
    """Loads CSV fixtures from local examples/fixtures/ or benchmark_corpus/."""

    def __init__(self, fixture_dir: Optional[Path | str] = None):
        self.fixture_dir = Path(fixture_dir) if fixture_dir else Path(__file__).resolve().parent.parent.parent / "examples" / "fixtures"

    def get_snapshot(self, metric_id: str) -> Dict[str, Any]:
        fixtures: Dict[str, Any] = {}
        if self.fixture_dir.exists():
            for p in self.fixture_dir.glob("*.csv"):
                fixtures[p.stem] = p
        return fixtures


class ReplayWorker:
    """Consumes firewall audit logs and checks if queries have untested semantic blind spots."""

    def __init__(self, contract_dir: str | Path, snapshot_provider: Optional[SnapshotProvider] = None):
        self.contract_dir = Path(contract_dir)
        self.snapshot_provider = snapshot_provider or LocalFixtureSnapshotProvider()

    def process_trace(self, trace_json: str | Dict[str, Any]) -> Optional[ReplayResult]:
        trace = json.loads(trace_json) if isinstance(trace_json, str) else trace_json

        # Replay only queries that were ALLOWED or AUDITED (passed the firewall)
        decision = trace.get("decision")
        if decision not in ("ALLOW", "AUDIT"):
            return None

        trace_id = trace.get("trace_id", "trace-unknown")
        metric_id = trace.get("metric_id")
        original_sql = trace.get("sql") or trace.get("original_sql")

        if not metric_id or not original_sql:
            logger.warning(f"Trace {trace_id} missing metric_id or sql.")
            return None

        # 1. Load Metric Contract
        contract_path = self._find_contract_path(metric_id)
        if not contract_path or not contract_path.exists():
            logger.warning(f"No contract file found for metric '{metric_id}'.")
            return None

        data = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        metric_def = MetricDefinition(**data)

        # 2. Fetch Fixtures
        fixtures = self.snapshot_provider.get_snapshot(metric_id)
        if not fixtures:
            logger.warning(f"No fixture data found for metric '{metric_id}'.")
            return None

        # 3. Build Semantic Assertions from Contract
        assertions_list = []
        if metric_def.invariants and metric_def.invariants.population:
            for req_filter in metric_def.invariants.population.required_filters:
                assertions_list.append(RequiredPopulationAssertion(
                    name=f"Population: {req_filter}",
                    required_filter=req_filter,
                    source_table="transactions",
                    join_key="customer_id"
                ))

        # Always include a baseline metric value bound assertion if available
        assertions_list.append(MetricValueAssertion(
            name="Metric Value Non-Zero",
            column=metric_def.metric,
            min_value=0.0,
        ))
        suite = AssertionSuite(name=f"contract_suite_{metric_id}", assertions=assertions_list)

        # 4. Generate AST Mutations
        engine = MutationEngine(base_sql=original_sql, dialect=metric_def.dialect)
        mutations = engine.generate_all_mutations()
        if not mutations:
            return None

        # 5. Execute Mutation Benchmark in DuckDB
        runner = DuckDBFixtureRunner(fixtures=fixtures)
        try:
            report = runner.run_assertion_benchmark(
                baseline_sql=original_sql,
                mutations=mutations,
                assertion_suite=suite,
            )
        finally:
            runner.close()

        # 6. Extract Blind Spots (Valid Defects that Survived)
        blind_spots: List[BlindSpot] = []
        for ev in report.evaluations:
            if ev.classification == MutationClassification.VALID_DEFECT_SURVIVED:
                blind_spots.append(BlindSpot(
                    mutation_id=ev.mutation_id,
                    mutation_type=ev.mutation_type,
                    description=ev.description,
                    empirical_variance_pct=ev.empirical_variance_pct,
                    summary=ev.summary,
                ))

        underspecified = len(blind_spots) > 0

        return ReplayResult(
            trace_id=trace_id,
            metric_id=metric_id,
            original_sql=original_sql,
            catch_score=report.effective_catch_score_pct,
            total_valid_defects=report.valid_defects_count,
            undetected_defects=len(blind_spots),
            blind_spots=blind_spots,
            contract_underspecified=underspecified,
        )

    def _find_contract_path(self, metric_id: str) -> Optional[Path]:
        direct = self.contract_dir / f"{metric_id}.yaml"
        if direct.exists():
            return direct
        for p in self.contract_dir.glob(f"**/{metric_id}.yaml"):
            return p
        return None
