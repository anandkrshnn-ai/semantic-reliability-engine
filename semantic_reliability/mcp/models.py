"""Data models and schemas for the SCOS Model Context Protocol (MCP) Server."""
import time
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
    timestamp_utc: float = Field(default_factory=time.time)
    method: str
    tool_name: Optional[str] = None
    resource_uri: Optional[str] = None
    metric_id: Optional[str] = None
    sql_sha256: Optional[str] = None
    decision: Optional[str] = None
    latency_ms: float = 0.0
    client_id: str = "mcp_client"


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
