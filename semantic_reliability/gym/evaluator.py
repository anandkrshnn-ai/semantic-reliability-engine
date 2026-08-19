import time
import uuid
import numpy as np
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel, Field
import duckdb
import pandas as pd

from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.firewall.engine import SemanticEvaluator, ContractRegistry
from semantic_reliability.firewall.policy import PolicyEngine
from semantic_reliability.firewall.models import EvaluateRequest, Decision


class EvalClassification(str, Enum):
    CONTRACT_COMPLIANT_RESULT_MATCH = "CONTRACT_COMPLIANT_RESULT_MATCH"
    CONTRACT_COMPLIANT_RESULT_MISMATCH = "CONTRACT_COMPLIANT_RESULT_MISMATCH"
    CONTRACT_VIOLATION_RESULT_MATCH = "CONTRACT_VIOLATION_RESULT_MATCH"
    CONTRACT_VIOLATION_RESULT_MISMATCH = "CONTRACT_VIOLATION_RESULT_MISMATCH"
    UNRESOLVED_CONTRACT = "UNRESOLVED_CONTRACT"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class AgentEvalRecord(BaseModel):
    example_id: str
    metric_id: str
    domain: str
    prompt: str
    generated_sql: str
    classification: EvalClassification
    execution_success: bool
    contract_compliant: bool
    result_correct: bool
    firewall_decision: str
    violations: List[str] = Field(default_factory=list)
    latency_ms: float = 0.0


class ConfusionMatrix(BaseModel):
    compliant_match: int = 0
    compliant_mismatch: int = 0
    violation_match: int = 0
    violation_mismatch: int = 0
    unresolved: int = 0
    execution_error: int = 0


class LatencySummary(BaseModel):
    mean_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    environment: str = "Local DuckDB evaluation runner (in-memory)"


class AgentBenchmarkReport(BaseModel):
    """Formal compliance evaluation report for an analytical Text-to-SQL agent."""
    model_name: str
    total_evaluations: int = 0
    execution_success_count: int = 0
    contract_compliant_count: int = 0
    result_correct_count: int = 0
    execution_success_rate_pct: float = 0.0
    contract_compliance_rate_pct: float = 0.0
    result_correctness_rate_pct: float = 0.0
    confusion_matrix: ConfusionMatrix = Field(default_factory=ConfusionMatrix)
    latency: LatencySummary = Field(default_factory=LatencySummary)
    domain_compliance: Dict[str, float] = Field(default_factory=dict)
    records: List[AgentEvalRecord] = Field(default_factory=list)
    protocol_disclaimer: str = "No external benchmark comparison is claimed; results are specific to the SRE frozen holdout protocol."

    def summary_markdown(self) -> str:
        md = [
            f"# 🤖 Agent Semantic Compliance Benchmark: {self.model_name}",
            "",
            "> **Disclaimer:** " + self.protocol_disclaimer,
            "",
            "## 📊 Primary Metrics",
            "",
            "| Evaluation Metric | SRE Protocol Result | Interpretation |",
            "| :--- | :---: | :--- |",
            f"| **Execution Success** | **{self.execution_success_rate_pct:.1f}%** ({self.execution_success_count}/{self.total_evaluations}) | Valid executable SQL queries |",
            f"| **Contract Compliance** | **{self.contract_compliance_rate_pct:.1f}%** ({self.contract_compliant_count}/{self.total_evaluations}) | Satisfies declared business invariants |",
            f"| **Result Correctness** | **{self.result_correctness_rate_pct:.1f}%** ({self.result_correct_count}/{self.total_evaluations}) | Correct output under reference oracle & fixture |",
            f"| **Mean Latency** | **{self.latency.mean_ms:.1f}ms** (p95: {self.latency.p95_ms:.1f}ms) | {self.latency.environment} |",
            "",
            "## 🧩 2x2 Semantic Compliance & Result Confusion Matrix",
            "",
            "| Category | Count | Proportion |",
            "| :--- | :---: | :---: |",
            f"| ✅ **Contract Compliant & Result Match** | {self.confusion_matrix.compliant_match} | {self._pct(self.confusion_matrix.compliant_match):.1f}% |",
            f"| ⚠️ **Contract Compliant but Result Mismatch** | {self.confusion_matrix.compliant_mismatch} | {self._pct(self.confusion_matrix.compliant_mismatch):.1f}% |",
            f"| 🚨 **Contract Violation but Result Match (Small Fixture)** | {self.confusion_matrix.violation_match} | {self._pct(self.confusion_matrix.violation_match):.1f}% |",
            f"| ❌ **Contract Violation & Result Mismatch** | {self.confusion_matrix.violation_mismatch} | {self._pct(self.confusion_matrix.violation_mismatch):.1f}% |",
            f"| ❓ **Unresolved (Incomplete Contract)** | {self.confusion_matrix.unresolved} | {self._pct(self.confusion_matrix.unresolved):.1f}% |",
            f"| 💥 **Execution Error** | {self.confusion_matrix.execution_error} | {self._pct(self.confusion_matrix.execution_error):.1f}% |",
            "",
            "## 🏢 Domain-Specific Compliance",
            "",
            "| Domain | Compliance Rate |",
            "| :--- | :---: |",
        ]
        for domain, rate in self.domain_compliance.items():
            md.append(f"| {domain.capitalize()} | {rate:.1f}% |")

        return "\n".join(md)

    def _pct(self, count: int) -> float:
        return (count / self.total_evaluations * 100.0) if self.total_evaluations > 0 else 0.0


class BaselineAgentEvaluator:
    """Evaluates agent-generated SQL against SRE Semantic Firewall and ground-truth fixtures."""

    def __init__(self, registry: ContractRegistry, strict_mode: bool = False, float_tol: float = 1e-4):
        self.registry = registry
        self.firewall = SemanticEvaluator(registry=registry, policy=PolicyEngine(strict_mode=strict_mode))
        self.float_tol = float_tol

    def evaluate_candidate(
        self,
        metric_def: MetricDefinition,
        generated_sql: str,
        fixture_df: Optional[pd.DataFrame] = None,
        table_name: str = "transactions",
        example_id: str = "eval_001",
    ) -> AgentEvalRecord:
        t0 = time.perf_counter()

        # Step 1: Pre-Execution Firewall Check
        req = EvaluateRequest(
            request_id=f"req-{uuid.uuid4()}",
            sql=generated_sql,
            metric_id=metric_def.metric,
            agent_id="test_agent",
            dialect=metric_def.dialect or "postgres",
        )
        resp = self.firewall.evaluate(req)
        contract_compliant = (resp.decision == Decision.ALLOW)

        # Step 2: Database Execution Check & Result Comparison
        con = duckdb.connect(":memory:")
        exec_success = False
        result_match = False

        if fixture_df is not None:
            try:
                con.register(table_name, fixture_df)
                res_cand = con.execute(generated_sql).df()
                exec_success = True

                res_true = con.execute(metric_def.sql).df()
                result_match = self._compare_dataframes(res_cand, res_true)
            except Exception:
                exec_success = False

        con.close()
        latency = (time.perf_counter() - t0) * 1000.0

        # Step 3: Classify into formal taxonomy
        classification = self._classify(exec_success, contract_compliant, result_match, bool(resp.violations))

        return AgentEvalRecord(
            example_id=example_id,
            metric_id=metric_def.metric,
            domain=metric_def.metadata.get("domain", metric_def.tags[0] if metric_def.tags else "general"),
            prompt=metric_def.description or f"Calculate {metric_def.metric}",
            generated_sql=generated_sql,
            classification=classification,
            execution_success=exec_success,
            contract_compliant=contract_compliant,
            result_correct=result_match,
            firewall_decision=resp.decision.value,
            violations=[v.rule for v in resp.violations],
            latency_ms=round(latency, 2),
        )

    def _compare_dataframes(self, df_cand: pd.DataFrame, df_true: pd.DataFrame) -> bool:
        """Order-insensitive, numeric-tolerant canonical row dataframe comparator."""
        if df_cand is None or df_true is None:
            return False
        if df_cand.empty and df_true.empty:
            return True
        if df_cand.empty != df_true.empty:
            return False
        if len(df_cand) != len(df_true) or df_cand.shape[1] != df_true.shape[1]:
            return False

        try:
            def canonical_row(row, cols):
                items = []
                for c in cols:
                    val = row[c]
                    if pd.isna(val) or val is None:
                        items.append(f"{c}:__NULL__")
                    elif isinstance(val, (int, float, np.number)):
                        rounded = round(float(val), 4)
                        items.append(f"{c}:{rounded}")
                    else:
                        items.append(f"{c}:{str(val).strip()}")
                return tuple(items)

            c_cols = sorted(df_cand.columns) if set(df_cand.columns) == set(df_true.columns) else list(df_cand.columns)
            t_cols = sorted(df_true.columns) if set(df_cand.columns) == set(df_true.columns) else list(df_true.columns)

            c_rows = sorted([canonical_row(row, c_cols) for _, row in df_cand.iterrows()])
            t_rows = sorted([canonical_row(row, t_cols) for _, row in df_true.iterrows()])

            return c_rows == t_rows
        except Exception:
            return False

    def _classify(self, exec_success: bool, contract_compliant: bool, result_match: bool, has_violations: bool) -> EvalClassification:
        if not exec_success:
            return EvalClassification.EXECUTION_ERROR
        if contract_compliant and result_match:
            return EvalClassification.CONTRACT_COMPLIANT_RESULT_MATCH
        if contract_compliant and not result_match:
            return EvalClassification.CONTRACT_COMPLIANT_RESULT_MISMATCH
        if not contract_compliant and result_match:
            return EvalClassification.CONTRACT_VIOLATION_RESULT_MATCH
        if not contract_compliant and not result_match:
            return EvalClassification.CONTRACT_VIOLATION_RESULT_MISMATCH
        return EvalClassification.UNRESOLVED_CONTRACT

    def run_benchmark(
        self,
        candidates: List[Dict[str, Any]],
        model_name: str = "Baseline-Agent",
    ) -> AgentBenchmarkReport:
        records: List[AgentEvalRecord] = []
        domain_counts: Dict[str, List[bool]] = {}
        matrix = ConfusionMatrix()
        latencies: List[float] = []

        for item in candidates:
            rec = self.evaluate_candidate(
                metric_def=item["metric_def"],
                generated_sql=item["generated_sql"],
                fixture_df=item.get("fixture_df"),
                table_name=item.get("table_name", "transactions"),
                example_id=item.get("example_id", f"eval_{len(records)+1}"),
            )
            records.append(rec)
            latencies.append(rec.latency_ms)
            domain_counts.setdefault(rec.domain, []).append(rec.contract_compliant)

            if rec.classification == EvalClassification.CONTRACT_COMPLIANT_RESULT_MATCH:
                matrix.compliant_match += 1
            elif rec.classification == EvalClassification.CONTRACT_COMPLIANT_RESULT_MISMATCH:
                matrix.compliant_mismatch += 1
            elif rec.classification == EvalClassification.CONTRACT_VIOLATION_RESULT_MATCH:
                matrix.violation_match += 1
            elif rec.classification == EvalClassification.CONTRACT_VIOLATION_RESULT_MISMATCH:
                matrix.violation_mismatch += 1
            elif rec.classification == EvalClassification.EXECUTION_ERROR:
                matrix.execution_error += 1
            else:
                matrix.unresolved += 1

        total = len(records)
        exec_count = sum(1 for r in records if r.execution_success)
        comp_count = sum(1 for r in records if r.contract_compliant)
        corr_count = sum(1 for r in records if r.result_correct)

        l_arr = np.array(latencies) if latencies else np.array([0.0])
        lat_summary = LatencySummary(
            mean_ms=round(float(np.mean(l_arr)), 2),
            p50_ms=round(float(np.percentile(l_arr, 50)), 2),
            p95_ms=round(float(np.percentile(l_arr, 95)), 2),
            p99_ms=round(float(np.percentile(l_arr, 99)), 2),
        )

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
            execution_success_rate_pct=round((exec_count / total * 100.0) if total > 0 else 0.0, 1),
            contract_compliance_rate_pct=round((comp_count / total * 100.0) if total > 0 else 0.0, 1),
            result_correctness_rate_pct=round((corr_count / total * 100.0) if total > 0 else 0.0, 1),
            confusion_matrix=matrix,
            latency=lat_summary,
            domain_compliance=domain_comp,
            records=records,
        )
