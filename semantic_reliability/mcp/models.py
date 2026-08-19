"""Data models and schemas for the SCOS Model Context Protocol (MCP) Server."""
import time
import json
import hashlib
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class CallerIdentity(BaseModel):
    """Authenticated caller identity with tenant and domain authorization bindings."""
    client_id: str = "mcp_anonymous"
    tenant_id: str = "default_tenant"
    allowed_domains: Optional[List[str]] = None
    role: str = "reader"
    authenticated: bool = False


class McpToolDefinition(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any]


class McpResourceDefinition(BaseModel):
    uri: str
    name: str
    description: str
    mimeType: str = "application/json"


class McpPromptArgument(BaseModel):
    name: str
    description: str
    required: bool = True


class McpPromptDefinition(BaseModel):
    name: str
    description: str
    arguments: List[McpPromptArgument] = Field(default_factory=list)


class McpAuditEvent(BaseModel):
    """A single hash-chained, tamper-evident audit event record."""
    event_id: str
    sequence_num: int = 0
    timestamp_utc: float = Field(default_factory=time.time)
    method: str
    tool_name: Optional[str] = None
    resource_uri: Optional[str] = None
    metric_id: Optional[str] = None
    tenant_id: str = "default_tenant"
    domain: Optional[str] = None
    sql_sha256: Optional[str] = None
    decision: Optional[str] = None
    latency_ms: float = 0.0
    client_id: str = "mcp_client"
    key_id: str = "sre-audit-key-2026-01"
    previous_event_hash: str = "0000000000000000000000000000000000000000000000000000000000000000"
    event_hash: str = ""

    def compute_hash(self) -> str:
        """Computes cryptographic hash over previous_event_hash + canonical event JSON."""
        data = {
            "event_id": self.event_id,
            "sequence_num": self.sequence_num,
            "timestamp_utc": self.timestamp_utc,
            "method": self.method,
            "tool_name": self.tool_name,
            "resource_uri": self.resource_uri,
            "metric_id": self.metric_id,
            "tenant_id": self.tenant_id,
            "domain": self.domain,
            "sql_sha256": self.sql_sha256,
            "decision": self.decision,
            "latency_ms": self.latency_ms,
            "client_id": self.client_id,
            "key_id": self.key_id,
            "previous_event_hash": self.previous_event_hash,
        }
        payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class AuditCheckpoint(BaseModel):
    """Cryptographically anchored periodic checkpoint over the audit hash chain."""
    checkpoint_id: str
    sequence_end: int
    last_event_hash: str
    checkpoint_timestamp: float = Field(default_factory=time.time)
    key_id: str = "sre-audit-key-2026-01"
    total_events_verified: int = 0
    checkpoint_signature: str = ""

    def compute_signature(self, signing_key: str = "sre-audit-signing-secret") -> str:
        payload = f"{self.checkpoint_id}:{self.sequence_end}:{self.last_event_hash}:{self.checkpoint_timestamp}:{self.key_id}:{signing_key}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SqlValidationResult(BaseModel):
    metric_id: str
    contract_version: str
    compliant: bool
    decision: str
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    execution_performed: bool = False
    policy_version: str = "scos-v1.0.0"
    sql_sha256: str
    latency_ms: float = 0.0
