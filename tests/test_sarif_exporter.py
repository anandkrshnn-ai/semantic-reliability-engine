import pytest
import json
from pathlib import Path
from semantic_reliability.harness.sarif_exporter import SARIFExporter
from semantic_reliability.drift.detector import SemanticDriftDetector

BASE_SQL = "SELECT * FROM t WHERE status = 'active'"
CAND_SQL = "SELECT * FROM t"


def test_sarif_generation():
    drifts = SemanticDriftDetector.analyze(BASE_SQL, CAND_SQL)
    sarif = SARIFExporter.from_drifts(drifts, file_path="models/my_model.sql")

    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"]) == 1
    assert len(sarif["runs"][0]["results"]) == len(drifts)
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "Semantic Reliability Engine"


def test_sarif_export_file(tmp_path):
    drifts = SemanticDriftDetector.analyze(BASE_SQL, CAND_SQL)
    out_file = tmp_path / "test.sarif"
    exported = SARIFExporter.export_to_file(drifts, out_file, file_path="models/my_model.sql")

    assert exported.exists()
    content = json.loads(exported.read_text(encoding="utf-8"))
    assert content["version"] == "2.1.0"
