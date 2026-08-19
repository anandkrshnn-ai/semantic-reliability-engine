"""Security, privacy, and audit boundaries for SCOS MCP Server."""
import hashlib
import logging
import time
import json
from typing import Any, Dict, Optional

# Configure structured audit logger
audit_logger = logging.getLogger("scos.audit")
if not audit_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('{"time": "%(asctime)s", "event": "scos_audit", "data": %(message)s}'))
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)

MAX_SQL_LENGTH = 50_000   # 50KB limit
MAX_PAYLOAD_SIZE = 100_000 # 100KB limit
REQUEST_TIMEOUT_SEC = 5.0


def hash_sql(sql: str) -> str:
    """Hashes SQL to prevent raw PII/proprietary logic leakage in logs."""
    return hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()


def enforce_limits(payload: dict) -> None:
    """Enforces request size and SQL length limits."""
    size = len(json.dumps(payload))
    if size > MAX_PAYLOAD_SIZE:
        raise ValueError(f"Payload size {size} exceeds limit {MAX_PAYLOAD_SIZE}")

    sql = payload.get("sql", "")
    if len(sql) > MAX_SQL_LENGTH:
        raise ValueError(f"SQL length {len(sql)} exceeds limit {MAX_SQL_LENGTH}")


def log_audit_event(tool_name: str, payload: dict, result: Any, latency_ms: float, previous_hash: str = "0" * 64) -> str:
    """Emits structured JSON audit event with cryptographic hash chaining."""
    safe_payload = payload.copy() if isinstance(payload, dict) else {}
    if "sql" in safe_payload:
        safe_payload["sql_hash"] = hash_sql(safe_payload["sql"])
        del safe_payload["sql"]  # Redact raw SQL from logs

    data = {
        "tool": tool_name,
        "payload": safe_payload,
        "latency_ms": round(latency_ms, 2),
        "timestamp": time.time(),
        "previous_hash": previous_hash,
    }
    event_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    event_hash = hashlib.sha256((previous_hash + event_json).encode("utf-8")).hexdigest()

    data["event_hash"] = event_hash
    audit_logger.info(json.dumps(data))
    return event_hash
