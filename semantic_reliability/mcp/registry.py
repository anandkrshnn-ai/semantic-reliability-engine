"""Read-only SCOS Contract Registry with URN and URI resolution."""
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from semantic_reliability.compiler.compiler import MetricCompiler
from semantic_reliability.compiler.schema import MetricDefinition


class SCOSRegistry:
    """Read-only registry for SCOS contracts with URN mapping and URI resolution."""

    def __init__(self, contracts_dir: str | Path):
        self.contracts_dir = Path(contracts_dir)
        self._cache: Dict[str, MetricDefinition] = {}
        self._raw_cache: Dict[str, MetricDefinition] = {}
        self._load_all()

    def _load_all(self):
        if not self.contracts_dir.exists():
            return

        for path in self.contracts_dir.rglob("*.yaml"):
            if path.name.startswith("assertions_") or path.name == "validity_policy.yaml":
                continue
            try:
                comp = MetricCompiler.from_yaml_file(path)
                metric = comp.definition
                domain = metric.metadata.get("domain", metric.tags[0] if metric.tags else "default")
                urn = f"urn:scos:{domain}:{metric.metric}"
                self._cache[urn] = metric
                self._raw_cache[metric.metric] = metric
            except Exception:
                continue

    def list_metrics(self) -> List[str]:
        return list(self._cache.keys())

    def get_contract(self, metric_id: str) -> MetricDefinition:
        # Support both URN (urn:scos:domain:metric) and raw metric_id (metric)
        if metric_id in self._cache:
            return self._cache[metric_id]
        if metric_id in self._raw_cache:
            return self._raw_cache[metric_id]
        raise KeyError(f"Metric '{metric_id}' not found in SCOS registry")

    def resolve_uri(self, uri: str) -> dict:
        """Resolves scos:// URIs to JSON payloads."""
        # Format: scos://contracts/{domain}/{metric_name}/{version}
        clean_uri = uri.replace("scos://", "")
        parts = clean_uri.split("/")
        if parts[0] == "contracts" and len(parts) >= 3:
            domain = parts[1]
            metric_name = parts[2]
            urn = f"urn:scos:{domain}:{metric_name}"
            metric = self.get_contract(urn)
            if len(parts) >= 4 and parts[3] == "invariants":
                return metric.invariants.model_dump() if metric.invariants else {}
            return metric.model_dump()

        if clean_uri == "policies/semantic-gate/1.0":
            return {
                "uri": uri,
                "policy_version": "1.0",
                "strict_mode_default": True,
                "allowed_severities": ["INFO", "LOW"],
                "blocking_severities": ["HIGH", "CRITICAL", "FATAL"],
            }

        raise ValueError(f"Unsupported URI format: {uri}")
