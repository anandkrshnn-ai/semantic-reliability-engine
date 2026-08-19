import logging
from typing import List, Literal, Optional, Any
from pydantic import BaseModel, Field
import duckdb

from semantic_reliability.compiler.schema import (
    MetricDefinition,
    MetricProbes,
    PopulationStabilityProbe,
    SemanticImplicationProbe,
)

logger = logging.getLogger("sre.probes")


class ProbeSignal(BaseModel):
    probe_type: str
    target: str
    status: Literal["HEALTHY", "WARNING", "CRITICAL"]
    current_value: float
    expected_value: float
    deviation: float
    message: str
    likely_cause: str


class StatisticalProbeEngine:
    """Executes declarative statistical probes against live warehouse connections or data snapshots."""

    def __init__(self, conn: duckdb.DuckDBPyConnection, table_name: str = "transactions"):
        self.conn = conn
        self.table = table_name

    def run_all(self, definition: MetricDefinition) -> List[ProbeSignal]:
        signals: List[ProbeSignal] = []
        if not definition.probes:
            return signals

        for probe in definition.probes.population_stability:
            signals.append(self._check_population(probe))

        for probe in definition.probes.implications:
            signals.append(self._check_implication(probe))

        return signals

    def _check_population(self, probe: PopulationStabilityProbe) -> ProbeSignal:
        """
        Checks: SELECT COUNT(CASE WHEN col = val THEN 1 END) / COUNT(*) FROM table
        Computes binomial Z-score against declared baseline_rate.
        """
        val_str = f"'{probe.target_value}'" if isinstance(probe.target_value, str) else str(probe.target_value)
        query = f"""
            SELECT 
                COUNT(CASE WHEN "{probe.column}" = {val_str} THEN 1 END) as match_count,
                COUNT(*) as total_count
            FROM {self.table}
        """
        try:
            res = self.conn.execute(query).fetchone()
            match_count, total_count = res[0], res[1]
            current_rate = (match_count / total_count) if total_count > 0 else 0.0

            p = probe.baseline_rate
            n = total_count
            std_dev = (p * (1.0 - p) / n) ** 0.5 if (n > 0 and 0.0 < p < 1.0) else 0.0
            z_score = abs(current_rate - p) / std_dev if std_dev > 0 else 0.0

            status: Literal["HEALTHY", "WARNING", "CRITICAL"] = "HEALTHY"
            if z_score > probe.threshold_std_dev:
                status = "CRITICAL" if z_score > 5.0 else "WARNING"

            return ProbeSignal(
                probe_type="Population Stability",
                target=f"{probe.column} = {val_str}",
                status=status,
                current_value=round(current_rate, 4),
                expected_value=round(p, 4),
                deviation=round(z_score, 2),
                message=f"Rate is {current_rate:.2%} (Expected {p:.2%}, Z={z_score:.2f})",
                likely_cause="Upstream definition of categorical value changed or population mix shifted.",
            )
        except Exception as e:
            return ProbeSignal(
                probe_type="Population Stability",
                target=probe.column,
                status="CRITICAL",
                current_value=0.0,
                expected_value=probe.baseline_rate,
                deviation=0.0,
                message=f"Execution error: {str(e)}",
                likely_cause="Schema change, missing table, or missing column.",
            )

    def _check_implication(self, probe: SemanticImplicationProbe) -> ProbeSignal:
        """
        Checks: P(Condition B | Condition A)
        E.g., P(mrr_amount > 0 | status = 'active')
        """
        op = probe.implication_operator.upper()
        cond_val_str = f"'{probe.condition_value}'" if isinstance(probe.condition_value, str) else str(probe.condition_value)

        if op == "IS NOT NULL":
            val_clause = "IS NOT NULL"
        else:
            imp_val_str = f"'{probe.implication_value}'" if isinstance(probe.implication_value, str) else str(probe.implication_value)
            val_clause = f"{probe.implication_operator} {imp_val_str}"

        query = f"""
            SELECT 
                COUNT(CASE WHEN "{probe.condition_column}" = {cond_val_str} THEN 1 END) as condition_total,
                COUNT(CASE WHEN "{probe.condition_column}" = {cond_val_str} AND "{probe.implication_column}" {val_clause} THEN 1 END) as implication_match
            FROM {self.table}
        """
        try:
            res = self.conn.execute(query).fetchone()
            cond_total, imp_match = res[0], res[1]

            confidence = (imp_match / cond_total) if cond_total > 0 else 0.0
            drop = probe.baseline_confidence - confidence

            status: Literal["HEALTHY", "WARNING", "CRITICAL"] = "HEALTHY"
            if drop > probe.threshold_drop:
                status = "CRITICAL" if drop > 0.20 else "WARNING"

            target_repr = f"{probe.condition_column}={cond_val_str} IMPLIES {probe.implication_column} {val_clause}"
            return ProbeSignal(
                probe_type="Semantic Implication",
                target=target_repr,
                status=status,
                current_value=round(confidence, 4),
                expected_value=round(probe.baseline_confidence, 4),
                deviation=round(drop, 4),
                message=f"Confidence dropped to {confidence:.2%} (Baseline {probe.baseline_confidence:.2%})",
                likely_cause="Decoupling of business attributes. E.g., 'Active' users now include 'Free Trial' (zero revenue).",
            )
        except Exception as e:
            return ProbeSignal(
                probe_type="Semantic Implication",
                target=probe.condition_column,
                status="CRITICAL",
                current_value=0.0,
                expected_value=probe.baseline_confidence,
                deviation=0.0,
                message=f"Execution error: {str(e)}",
                likely_cause="Schema change or missing column.",
            )
