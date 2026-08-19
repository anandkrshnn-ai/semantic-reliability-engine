import json
from typing import List, Dict, Any, Optional
from pathlib import Path

from semantic_reliability.drift.rules import SemanticDrift, DriftSeverity
from semantic_reliability.compiler.contracts import ContractEvaluationResult


class SARIFExporter:
    """Generates standard SARIF 2.1.0 JSON reports for GitHub Code Scanning / Security Tab."""

    SCHEMA_URI = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
    TOOL_NAME = "Semantic Reliability Engine"
    TOOL_VERSION = "0.1.0"

    @classmethod
    def from_drifts(
        cls,
        drifts: List[SemanticDrift],
        file_path: str = "models/model.sql",
    ) -> Dict[str, Any]:
        """Convert a list of SemanticDrift instances into a standard SARIF JSON document."""
        rules_map: Dict[str, Dict[str, Any]] = {}
        results: List[Dict[str, Any]] = []

        severity_to_sarif_level = {
            DriftSeverity.FATAL: "error",
            DriftSeverity.CRITICAL: "error",
            DriftSeverity.HIGH: "error",
            DriftSeverity.MEDIUM: "warning",
            DriftSeverity.LOW: "note",
            DriftSeverity.INFO: "none",
        }

        for idx, d in enumerate(drifts, 1):
            rule_id = f"SRE-{d.drift_type.value}"
            if rule_id not in rules_map:
                rules_map[rule_id] = {
                    "id": rule_id,
                    "name": d.drift_type.value,
                    "shortDescription": {"text": d.summary},
                    "fullDescription": {"text": f"{d.summary} - {d.business_impact}"},
                    "defaultConfiguration": {"level": severity_to_sarif_level.get(d.severity, "warning")},
                    "help": {
                        "text": f"Remediation: {d.remediation or 'Review logic against canonical definition.'}",
                    },
                }

            result_entry = {
                "ruleId": rule_id,
                "level": severity_to_sarif_level.get(d.severity, "warning"),
                "message": {
                    "text": f"[{d.severity.value}] {d.summary}: {d.details} Impact: {d.business_impact}"
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": file_path.replace("\\", "/"),
                            },
                            "region": {
                                "startLine": 1,
                                "startColumn": 1,
                            },
                        }
                    }
                ],
            }
            results.append(result_entry)

        sarif_doc = {
            "$schema": cls.SCHEMA_URI,
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": cls.TOOL_NAME,
                            "version": cls.TOOL_VERSION,
                            "informationUri": "https://github.com/anandkrshnn-ai/semantic-reliability-engine",
                            "rules": list(rules_map.values()),
                        }
                    },
                    "results": results,
                }
            ],
        }

        return sarif_doc

    @classmethod
    def export_to_file(cls, drifts: List[SemanticDrift], output_file: str | Path, file_path: str = "models/model.sql") -> Path:
        """Write SARIF output to file."""
        doc = cls.from_drifts(drifts, file_path=file_path)
        out_p = Path(output_file)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
        return out_p
