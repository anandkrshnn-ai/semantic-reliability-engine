"""Data models and schemas for the SCOS Model Context Protocol (MCP) Server."""
import time
import json
import hashlib
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


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
    event_id: str
    sequence_num: int = 0
    timestamp_utc: float = Field(default_factory=time.time)
    method: str
    tool_name: Optional[str] = None
    resource_uri: Optional[str] = None
    metric_id: Optional[str] = None
    domain: Optional[str] = None
    sql_sha256: Optional[str] = None
    decision: Optional[str] = None
    latency_ms: float = 0.0
    client_id: str = "mcp_client"
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
            "domain": self.domain,
            "sql_sha256": self.sql_sha256,
            "decision": self.decision,
            "latency_ms": self.latency_ms,
            "client_id": self.client_id,
            "previous_event_hash": self.previous_event_hash,
        }
        payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


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
