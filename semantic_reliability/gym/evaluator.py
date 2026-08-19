import time
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
import duckdb
import pandas as pd

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.firewall.engine import SemanticEvaluator, ContractRegistry
from semantic_reliability.firewall.models import EvaluateRequest, Decision


class AgentEvalRecord(BaseModel):
    example_id: str
    metric_id: str
    domain: str
    prompt: str
    generated_sql: str
    execution_success: bool
    contract_compliant: bool
    firewall_decision: str
    violations: List[str] = Field(default_factory=list)
    result_correct: bool = False
    latency_ms: float = 0.0


class AgentBenchmarkReport(BaseModel):
    """Formal compliance evaluation report for an analytical Text-to-SQL agent."""
    model_name: str
    total_evaluations: int = 0
    execution_success_count: int = 0
    contract_compliant_count: int = 0
    result_correct_count: int = 0
    avg_latency_ms: float = 0.0
    execution_success_rate_pct: float = 0.0
    contract_compliance_rate_pct: float = 0.0
    result_correctness_rate_pct: float = 0.0
    domain_compliance: Dict[str, float] = Field(default_factory=dict)
    records: List[AgentEvalRecord] = Field(default_factory=list)

    def summary_markdown(self) -> str:
        md = [
            f"# 🤖 Agent Semantic Compliance Benchmark: {self.model_name}",
            "",
            "| Evaluation Metric | Score | Industry Benchmark |",
            "| :--- | :---: | :---: |",
            f"| **Execution Success Rate** | **{self.execution_success_rate_pct:.1f}%** ({self.execution_success_count}/{self.total_evaluations}) | >90.0% (Spider/BIRD) |",
            f"| **Semantic Contract Compliance** | **{self.contract_compliance_rate_pct:.1f}%** ({self.contract_compliant_count}/{self.total_evaluations}) | Expected Baseline <40% |",
            f"| **Result Correctness vs Truth** | **{self.result_correctness_rate_pct:.1f}%** ({self.result_correct_count}/{self.total_evaluations}) | Ground-Truth Oracle |",
            f"| **Average Latency** | **{self.avg_latency_ms:.1f}ms** | Sub-second Gateway |",
            "",
            "### Domain-Specific Semantic Compliance",
            "",
            "| Domain | Compliance Rate |",
            "| :--- | :---: |",
        ]
        for domain, rate in self.domain_compliance.items():
            md.append(f"| {domain.capitalize()} | {rate:.1f}% |")

        return "\n".join(md)


class BaselineAgentEvaluator:
    """Evaluates agent-generated SQL against SRE Semantic Firewall and ground-truth fixtures."""

    def __init__(self, registry: ContractRegistry, strict_mode: bool = False):
        from semantic_reliability.firewall.policy import PolicyEngine
        self.registry = registry
        self.firewall = SemanticEvaluator(registry=registry, policy=PolicyEngine(strict_mode=strict_mode))

    def evaluate_candidate(
        self,
        metric_def: MetricDefinition,
        generated_sql: str,
        fixture_df: Optional[pd.DataFrame] = None,
        table_name: str = "transactions",
        example_id: str = "eval_001",
    ) -> AgentEvalRecord:
        t0 = time.perf_counter()

        import uuid
        # Step 1: Pre-Execution Firewall Check
        req = EvaluateRequest(
            request_id=f"req-{uuid.uuid4()}",
            sql=generated_sql,
            metric_id=metric_def.metric,
            agent_id="test_agent",
            dialect=metric_def.dialect or "postgres",
        )
        resp = self.firewall.evaluate(req)

        # Step 2: Database Execution Check
        con = duckdb.connect(":memory:")
        exec_success = False
        result_correct = False

        if fixture_df is not None:
            try:
                con.register(table_name, fixture_df)
                res_cand = con.execute(generated_sql).df()
                exec_success = True

                # Compare with ground-truth SQL
                res_true = con.execute(metric_def.sql).df()
                if not res_cand.empty and not res_true.empty:
                    # Robust dataframe equality comparison
                    result_correct = res_cand.sort_index(axis=1).equals(res_true.sort_index(axis=1))
                elif res_cand.empty and res_true.empty:
                    result_correct = True
            except Exception:
                exec_success = False

        con.close()
        latency = (time.perf_counter() - t0) * 1000.0

        return AgentEvalRecord(
            example_id=example_id,
            metric_id=metric_def.metric,
            domain=metric_def.metadata.get("domain", metric_def.tags[0] if metric_def.tags else "general"),
            prompt=metric_def.description or f"Calculate {metric_def.metric}",
            generated_sql=generated_sql,
            execution_success=exec_success,
            contract_compliant=(resp.decision == Decision.ALLOW),
            firewall_decision=resp.decision.value,
            violations=[v.rule for v in resp.violations],
            result_correct=result_correct,
            latency_ms=round(latency, 2),
        )

    def run_benchmark(
        self,
        candidates: List[Dict[str, Any]],
        model_name: str = "Baseline-Agent",
    ) -> AgentBenchmarkReport:
        """Runs evaluation over a list of candidate items {metric_def, generated_sql, fixture_df}."""
        records: List[AgentEvalRecord] = []
        domain_counts: Dict[str, List[bool]] = {}

        for item in candidates:
            rec = self.evaluate_candidate(
                metric_def=item["metric_def"],
                generated_sql=item["generated_sql"],
                fixture_df=item.get("fixture_df"),
                table_name=item.get("table_name", "transactions"),
                example_id=item.get("example_id", f"eval_{len(records)+1}"),
            )
            records.append(rec)
            domain_counts.setdefault(rec.domain, []).append(rec.contract_compliant)

        total = len(records)
        exec_count = sum(1 for r in records if r.execution_success)
        comp_count = sum(1 for r in records if r.contract_compliant)
        corr_count = sum(1 for r in records if r.result_correct)
        avg_lat = (sum(r.latency_ms for r in records) / total) if total > 0 else 0.0

        domain_comp = {
            d: round((sum(bools) / len(bools)) * 100.0, 1)
            for d, bools in domain_counts.items()
        }

        return AgentBenchmarkReport(
            model_name=model_name,
            total_evaluations=total,
            execution_success_count=exec_count,
            contract_compliant_count=comp_count,
            result_correct_count=corr_count,
            avg_latency_ms=round(avg_lat, 2),
            execution_success_rate_pct=round((exec_count / total * 100.0) if total > 0 else 0.0, 1),
            contract_compliance_rate_pct=round((comp_count / total * 100.0) if total > 0 else 0.0, 1),
            result_correctness_rate_pct=round((corr_count / total * 100.0) if total > 0 else 0.0, 1),
            domain_compliance=domain_comp,
            records=records,
        )
