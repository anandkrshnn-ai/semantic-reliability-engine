"""dbt Manifest Resolver and Semantic Drift Checker with strict compilation validation."""
import json
from pathlib import Path
from enum import Enum
from typing import Tuple, Dict, Any, List

from semantic_reliability.compiler.compiler import MetricCompiler
from semantic_reliability.compiler.schema import MetricDefinition
from semantic_reliability.drift.detector import SemanticDriftDetector
from semantic_reliability.drift.rules import DriftSeverity, SemanticDrift


class NodeResolutionStatus(str, Enum):
    COMPILED_SQL_PRESENT = "COMPILED_SQL_PRESENT"
    COMPILED_SQL_ABSENT = "COMPILED_SQL_ABSENT"
    RAW_CODE_ONLY = "RAW_CODE_ONLY"
    NODE_NOT_FOUND = "NODE_NOT_FOUND"
    UNSUPPORTED_RESOURCE_TYPE = "UNSUPPORTED_RESOURCE_TYPE"


class DbtManifestResolver:
    """Extracts compiled SQL and dialect from dbt target/manifest.json."""

    def __init__(self, manifest_path: str | Path):
        p = Path(manifest_path)
        with open(p, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)

        self.default_dialect = self.manifest.get("metadata", {}).get("adapter_type", "bigquery")

    def resolve_model(self, model_name: str, require_compiled: bool = True) -> Tuple[str, str, str, NodeResolutionStatus]:
        """
        Resolves model from manifest.json.
        Returns (sql, dialect, node_id, status).
        """
        nodes = self.manifest.get("nodes", {})
        target_node_id = None
        target_node = None

        for node_id, node in nodes.items():
            if node.get("name") == model_name:
                target_node_id = node_id
                target_node = node
                break

        if not target_node:
            raise ValueError(f"Model '{model_name}' not found in manifest.json ({NodeResolutionStatus.NODE_NOT_FOUND.value})")

        if target_node.get("resource_type") != "model":
            raise ValueError(f"Node '{model_name}' is resource_type '{target_node.get('resource_type')}', expected 'model' ({NodeResolutionStatus.UNSUPPORTED_RESOURCE_TYPE.value})")

        dialect = target_node.get("config", {}).get("adapter_type", self.default_dialect)
        compiled = target_node.get("compiled_code") or target_node.get("compiled_sql")
        raw = target_node.get("raw_code") or target_node.get("raw_sql")

        if compiled and compiled.strip():
            return compiled.strip(), dialect, target_node_id, NodeResolutionStatus.COMPILED_SQL_PRESENT

        if require_compiled:
            raise ValueError(
                f"Model '{model_name}' ({target_node_id}) has no compiled SQL. "
                "Run `dbt compile` or `dbt build` first to generate target/manifest.json with compiled_sql."
            )

        if raw and raw.strip():
            return raw.strip(), dialect, target_node_id, NodeResolutionStatus.RAW_CODE_ONLY

        raise ValueError(f"Model '{model_name}' has neither compiled nor raw SQL code in manifest.")


class DbtSreChecker:
    """Orchestrates semantic drift checking for dbt models against metric contracts."""

    def __init__(self, manifest_path: str | Path):
        self.resolver = DbtManifestResolver(manifest_path)

    def check(self, model_name: str, contract_path: str | Path, require_compiled: bool = True) -> Dict[str, Any]:
        model_sql, dialect, node_id, status = self.resolver.resolve_model(model_name, require_compiled=require_compiled)
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
            "manifest_node": node_id,
            "resolution_status": status.value,
            "compiled_sql_available": (status == NodeResolutionStatus.COMPILED_SQL_PRESENT),
            "dialect": dialect,
            "contract": metric.metric,
            "drift_alerts": [d.model_dump() for d in drifts],
            "max_severity": max_sev.value,
            "has_critical_drift": sev_rank.get(max_sev, 0) >= sev_rank[DriftSeverity.CRITICAL],
            "decision": "DENY" if (sev_rank.get(max_sev, 0) >= sev_rank[DriftSeverity.CRITICAL]) else ("REQUIRE_REVIEW" if drifts else "ALLOW"),
        }
