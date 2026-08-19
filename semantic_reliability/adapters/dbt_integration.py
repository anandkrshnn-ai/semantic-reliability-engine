"""dbt Manifest Resolver and Semantic Drift Checker."""
import json
from pathlib import Path
from typing import Tuple, Dict, Any, List

from semantic_reliability.compiler.compiler import MetricCompiler
from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.drift.detector import SemanticDriftDetector
from semantic_reliability.drift.rules import DriftSeverity, SemanticDrift


class DbtManifestResolver:
    """Extracts compiled SQL and dialect from dbt manifest.json."""

    def __init__(self, manifest_path: str | Path):
        p = Path(manifest_path)
        with open(p, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)

        self.default_dialect = self.manifest.get("metadata", {}).get("adapter_type", "bigquery")

    def resolve_model(self, model_name: str) -> Tuple[str, str]:
        """Returns (compiled_sql, dialect)."""
        nodes = self.manifest.get("nodes", {})
        for node_id, node in nodes.items():
            if node.get("name") == model_name and node.get("resource_type") == "model":
                compiled = node.get("compiled_code") or node.get("compiled_sql")
                raw = node.get("raw_code") or node.get("raw_sql")
                dialect = node.get("config", {}).get("adapter_type", self.default_dialect)

                sql = compiled if compiled else raw
                if not sql:
                    raise ValueError(f"Model '{model_name}' has no compiled or raw SQL code in manifest.")
                return sql.strip(), dialect

        raise ValueError(f"Model '{model_name}' not found in manifest.json")


class DbtSreChecker:
    """Orchestrates semantic drift checking for dbt models against metric contracts."""

    def __init__(self, manifest_path: str | Path):
        self.resolver = DbtManifestResolver(manifest_path)

    def check(self, model_name: str, contract_path: str | Path) -> Dict[str, Any]:
        model_sql, dialect = self.resolver.resolve_model(model_name)
        contract_text = Path(contract_path).read_text(encoding="utf-8")
        compiler = MetricCompiler.from_yaml_str(contract_text)
        metric: MetricDefinition = compiler.definition

        # Ground truth SQL from contract
        ground_truth_sql = metric.sql

        # Run semantic drift detector
        drifts: List[SemanticDrift] = SemanticDriftDetector.analyze(
            original_sql=ground_truth_sql,
            candidate_sql=model_sql,
            dialect=dialect or metric.dialect or "bigquery",
        )

        # Map severities
        sev_rank = {
            DriftSeverity.INFO: 0,
            DriftSeverity.LOW: 1,
            DriftSeverity.MEDIUM: 2,
            DriftSeverity.HIGH: 3,
            DriftSeverity.CRITICAL: 4,
            DriftSeverity.FATAL: 5,
        }

        max_sev = DriftSeverity.INFO
        if drifts:
            max_sev = max(drifts, key=lambda d: sev_rank.get(d.severity, 0)).severity

        return {
            "model": model_name,
            "dialect": dialect,
            "contract": metric.metric,
            "drift_alerts": [d.model_dump() for d in drifts],
            "max_severity": max_sev.value,
            "has_critical_drift": sev_rank.get(max_sev, 0) >= sev_rank[DriftSeverity.CRITICAL],
        }
