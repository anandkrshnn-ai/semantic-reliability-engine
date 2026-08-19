import duckdb
import logging
from typing import List, Optional

from semantic_reliability.compiler.schema import MetricDefinition, MetricProbes, PopulationProbe, ImplicationProbe, NullDriftProbe
from .signals import SemanticProbeAlert

logger = logging.getLogger("sre.probes")


class StatisticalProbeEngine:
    """Executes declarative statistical probes against live warehouse connections or data snapshots."""

    def __init__(self, conn: duckdb.DuckDBPyConnection, table_name: str = "transactions"):
        self.conn = conn
        self.table = table_name

    def run_all(self, definition: MetricDefinition) -> List[SemanticProbeAlert]:
        alerts: List[SemanticProbeAlert] = []
        if not definition.probes:
            return alerts

        for p_probe in definition.probes.population:
            alert = self._check_population(p_probe, definition.metric)
            if alert:
                alerts.append(alert)

        for imp_probe in definition.probes.implications:
            alert = self._check_implication(imp_probe, definition.metric)
            if alert:
                alerts.append(alert)

        for null_probe in definition.probes.null_drift:
            alert = self._check_null_drift(null_probe, definition.metric)
            if alert:
                alerts.append(alert)

        return alerts

    def _check_population(self, probe: PopulationProbe, metric_id: str) -> Optional[SemanticProbeAlert]:
        if probe.target_value is None:
            val_clause = "IS NULL"
            query = f"SELECT COUNT(CASE WHEN \"{probe.column}\" {val_clause} THEN 1 END), COUNT(*) FROM {self.table}"
        else:
            val_clause = f"'{probe.target_value}'" if isinstance(probe.target_value, str) else str(probe.target_value)
            query = f"SELECT COUNT(CASE WHEN \"{probe.column}\" = {val_clause} THEN 1 END), COUNT(*) FROM {self.table}"

        try:
            res = self.conn.execute(query).fetchone()
            match_count, total_count = res[0], res[1]
            current_rate = (match_count / total_count) if total_count > 0 else 0.0

            deviation = abs(current_rate - probe.baseline_rate)
            if deviation > probe.tolerance:
                rel_change = ((current_rate - probe.baseline_rate) / probe.baseline_rate) * 100.0 if probe.baseline_rate > 0 else 0.0
                return SemanticProbeAlert(
                    signal_type=f"{probe.column}_population_rate_shift",
                    contract=metric_id,
                    baseline=round(probe.baseline_rate, 4),
                    current=round(current_rate, 4),
                    relative_change=round(rel_change, 1),
                    confidence="high" if deviation > (probe.tolerance * 2) else "medium",
                    likely_causes=[
                        "Upstream status mapping changed in source CRM/database",
                        "Cohort segmentation query filter shifted",
                        "Fixture / production sample population mix shifted",
                    ]
                )
        except Exception as e:
            logger.error(f"Population probe failed for {metric_id}: {str(e)}")
        return None

    def _check_implication(self, probe: ImplicationProbe, metric_id: str) -> Optional[SemanticProbeAlert]:
        cond_val = f"'{probe.condition_value}'" if isinstance(probe.condition_value, str) else str(probe.condition_value)

        if probe.implication_operator.upper() == "IS NOT NULL":
            imp_clause = f"\"{probe.implication_column}\" IS NOT NULL"
        else:
            imp_val = f"'{probe.implication_value}'" if isinstance(probe.implication_value, str) else str(probe.implication_value)
            imp_clause = f"\"{probe.implication_column}\" {probe.implication_operator} {imp_val}"

        query = f"""
            SELECT 
                COUNT(CASE WHEN \"{probe.condition_column}\" = {cond_val} THEN 1 END) as cond_total,
                COUNT(CASE WHEN \"{probe.condition_column}\" = {cond_val} AND {imp_clause} THEN 1 END) as imp_match
            FROM {self.table}
        """
        try:
            res = self.conn.execute(query).fetchone()
            cond_total, imp_match = res[0], res[1]
            confidence = (imp_match / cond_total) if cond_total > 0 else 0.0
            drop = probe.baseline_confidence - confidence

            if drop > probe.tolerance_drop:
                rel_change = (drop / probe.baseline_confidence) * 100.0 if probe.baseline_confidence > 0 else 0.0
                return SemanticProbeAlert(
                    signal_type=f"{probe.condition_column}_implies_{probe.implication_column}_decay",
                    contract=metric_id,
                    baseline=round(probe.baseline_confidence, 4),
                    current=round(confidence, 4),
                    relative_change=-round(rel_change, 1),
                    confidence="high" if drop > (probe.tolerance_drop * 2) else "medium",
                    likely_causes=[
                        "Decoupling of business attributes in upstream pipeline",
                        f"Definition of '{probe.condition_column}' expanded to include records violating implication ({imp_clause})",
                    ]
                )
        except Exception as e:
            logger.error(f"Implication probe failed for {metric_id}: {str(e)}")
        return None

    def _check_null_drift(self, probe: NullDriftProbe, metric_id: str) -> Optional[SemanticProbeAlert]:
        query = f"SELECT COUNT(CASE WHEN \"{probe.column}\" IS NULL THEN 1 END), COUNT(*) FROM {self.table}"
        try:
            res = self.conn.execute(query).fetchone()
            null_count, total_count = res[0], res[1]
            current_rate = (null_count / total_count) if total_count > 0 else 0.0

            deviation = abs(current_rate - probe.baseline_null_rate)
            if deviation > probe.tolerance:
                rel_change = ((current_rate - probe.baseline_null_rate) / probe.baseline_null_rate) * 100.0 if probe.baseline_null_rate > 0 else 0.0
                return SemanticProbeAlert(
                    signal_type=f"{probe.column}_null_rate_shift",
                    contract=metric_id,
                    baseline=round(probe.baseline_null_rate, 4),
                    current=round(current_rate, 4),
                    relative_change=round(rel_change, 1),
                    confidence="medium",
                    likely_causes=[
                        "Upstream ETL pipeline partial failure",
                        "Schema migration or unhandled column rename",
                        "Source system API payload schema changes",
                    ]
                )
        except Exception as e:
            logger.error(f"Null drift probe failed for {metric_id}: {str(e)}")
        return None
