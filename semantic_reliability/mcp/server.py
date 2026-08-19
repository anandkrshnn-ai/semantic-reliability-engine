"""SCOS Model Context Protocol (MCP) Server with Audit Hash-Chaining & Operational Hardening."""
import sys
import json
import logging
import uuid
from typing import Dict, Any, Optional, List
from pathlib import Path

from semantic_reliability.firewall.engine import ContractRegistry
from .models import McpAuditEvent
from .handlers import ScosMcpHandlers

logger = logging.getLogger("sre.mcp")


class ScosMcpServer:
    """Standard JSON-RPC 2.0 Model Context Protocol Server with Cryptographic Audit Hash Chaining."""

    SERVER_NAME = "scos-mcp-server"
    SERVER_VERSION = "1.0.0"
    PROTOCOL_VERSION = "2024-11-05"
    MAX_REQUEST_BYTES = 1_000_000
    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(
        self,
        registry: Optional[ContractRegistry] = None,
        contract_dir: Optional[str | Path] = None,
        allowed_domains: Optional[List[str]] = None,
        max_request_bytes: int = 1_000_000,
    ):
        if registry:
            self.registry = registry
        elif contract_dir:
            self.registry = ContractRegistry(contract_dir=str(contract_dir))
        else:
            self.registry = ContractRegistry()

        self.allowed_domains = allowed_domains
        self.handlers = ScosMcpHandlers(self.registry, allowed_domains=allowed_domains)
        self.audit_log: List[McpAuditEvent] = []
        self.max_request_bytes = max_request_bytes

    def handle_request(self, req: Dict[str, Any], raw_payload_len: Optional[int] = None) -> Dict[str, Any]:
        """Process a single JSON-RPC 2.0 request with strict error code mapping."""
        req_id = req.get("id") if isinstance(req, dict) else None

        if not isinstance(req, dict):
            return self._error_response(None, -32600, "Invalid Request: root payload must be a JSON object.")

        if raw_payload_len and raw_payload_len > self.max_request_bytes:
            return self._error_response(req_id, -32600, f"Payload size exceeds limit of {self.max_request_bytes} bytes.")

        method = req.get("method")
        params = req.get("params", {})

        if not method or not isinstance(method, str):
            return self._error_response(req_id, -32600, "Invalid Request: missing or invalid 'method' field.")

        if not isinstance(params, dict):
            return self._error_response(req_id, -32602, "Invalid Params: 'params' must be a JSON object.")

        try:
            if method == "initialize":
                client_proto = params.get("protocolVersion", self.PROTOCOL_VERSION)
                return self._success_response(req_id, {
                    "protocolVersion": client_proto,
                    "serverInfo": {
                        "name": self.SERVER_NAME,
                        "version": self.SERVER_VERSION,
                    },
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    }
                })

            elif method == "tools/list":
                tools = [t.model_dump() for t in self.handlers.list_tools()]
                return self._success_response(req_id, {"tools": tools})

            elif method == "tools/call":
                name = params.get("name")
                if not name:
                    return self._error_response(req_id, -32602, "Invalid params: missing tool 'name'.")

                args = params.get("arguments", {})
                if not isinstance(args, dict):
                    return self._error_response(req_id, -32602, "Invalid params: 'arguments' must be a dictionary.")

                try:
                    result = self.handlers.call_tool(name, args)
                except ValueError as ve:
                    return self._error_response(req_id, -32602, f"Invalid tool arguments: {str(ve)}")

                # Cryptographic Hash Chaining on Audit Log
                prev_hash = self.audit_log[-1].event_hash if self.audit_log else self.GENESIS_HASH
                audit = McpAuditEvent(
                    event_id=f"mcp-ev-{uuid.uuid4()}",
                    sequence_num=len(self.audit_log) + 1,
                    method="tools/call",
                    tool_name=name,
                    metric_id=args.get("metric_id"),
                    domain=result.get("domain"),
                    sql_sha256=result.get("sql_sha256"),
                    decision=result.get("decision"),
                    latency_ms=result.get("latency_ms", 0.0),
                    previous_event_hash=prev_hash,
                )
                audit.event_hash = audit.compute_hash()
                self.audit_log.append(audit)

                return self._success_response(req_id, {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]})

            elif method == "resources/list":
                res = [r.model_dump() for r in self.handlers.list_resources()]
                return self._success_response(req_id, {"resources": res})

            elif method == "resources/read":
                uri = params.get("uri")
                if not uri:
                    return self._error_response(req_id, -32602, "Invalid params: missing 'uri'.")
                try:
                    data = self.handlers.read_resource(uri)
                except ValueError as ve:
                    return self._error_response(req_id, -32602, str(ve))

                return self._success_response(req_id, {
                    "contents": [{
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(data, indent=2)
                    }]
                })

            elif method == "prompts/list":
                prompts = [p.model_dump() for p in self.handlers.list_prompts()]
                return self._success_response(req_id, {"prompts": prompts})

            elif method == "prompts/get":
                name = params.get("name")
                if not name:
                    return self._error_response(req_id, -32602, "Invalid params: missing prompt 'name'.")
                args = params.get("arguments", {})
                try:
                    prompt_text = self.handlers.get_prompt(name, args)
                except ValueError as ve:
                    return self._error_response(req_id, -32602, str(ve))

                return self._success_response(req_id, {
                    "description": f"Prompt: {name}",
                    "messages": [
                        {"role": "user", "content": {"type": "text", "text": prompt_text}}
                    ]
                })

            elif method == "notifications/initialized":
                return {}

            else:
                return self._error_response(req_id, -32601, f"Method not found: '{method}'")

        except Exception as e:
            logger.exception(f"Error handling MCP method {method}")
            return self._error_response(req_id, -32603, f"Internal error: {str(e)}")

    def verify_audit_chain(self) -> bool:
        """Cryptographically verifies the integrity of the audit log hash chain."""
        if not self.audit_log:
            return True

        for i, ev in enumerate(self.audit_log):
            expected_prev = self.audit_log[i - 1].event_hash if i > 0 else self.GENESIS_HASH
            if ev.previous_event_hash != expected_prev:
                return False
            if ev.event_hash != ev.compute_hash():
                return False
        return True

    def _success_response(self, req_id: Any, result: Any) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }

    def _error_response(self, req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
            }
        }

    def run_stdio(self):
        """Run standard stdio loop for local MCP client integration."""
        for line in sys.stdin:
            raw = line.strip()
            if not raw:
                continue
            try:
                req = json.loads(raw)
            except Exception as e:
                err = self._error_response(None, -32700, f"Parse error: {str(e)}")
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()
                continue

            resp = self.handle_request(req, raw_payload_len=len(raw))
            if resp:  # Notifications return empty dict
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
