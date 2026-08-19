import pytest
from pathlib import Path
from semantic_reliability.harness.protocol_verifier import ProtocolVerifier, ProtocolIntegrityResult


def test_holdout_protocol_verifier_runs():
    res = ProtocolVerifier.verify_holdout_protocol()
    assert isinstance(res, ProtocolIntegrityResult)
    assert res.declared_protocol.get("protocol_version") == "1.0"
    assert res.declared_protocol.get("freeze_tag") == "v1.0.0-phase6"


def test_holdout_protocol_detects_mismatched_commit(tmp_path):
    mock_proto = tmp_path / "mock_protocol.yaml"
    mock_proto.write_text("""
protocol_version: "1.0"
freeze_commit: "0000000000000000000000000000000000000000"
freeze_tag: "v0.0.0-mock"
""", encoding="utf-8")

    res = ProtocolVerifier.verify_holdout_protocol(protocol_path=mock_proto)
    if res.current_git_commit:
        assert res.integrity_status == "MODIFIED"
        assert res.is_frozen_baseline is False
