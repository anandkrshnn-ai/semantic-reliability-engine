"""SCOS Model Context Protocol (MCP) Server Implementation."""
import sys
import json
import logging
import uuid
from typing import Dict, Any, Optional
from pathlib import Path

from semantic_reliability.firewall.engine import ContractRegistry
from .models import McpAuditEvent
from .handlers import ScosMcpHandlers

logger = logging.getLogger("sre.mcp")


class ScosMcpServer:
    """Standard JSON-RPC 2.0 Model Context Protocol Server for SCOS Contracts."""

    SERVER_NAME = "scos-mcp-server"
    SERVER_VERSION = "1.0.0"
    PROTOCOL_VERSION = "2024-11-05"
    MAX_REQUEST_BYTES = 1_000_000

    def __init__(
        self,
        registry: Optional[ContractRegistry] = None,
        contract_dir: Optional[str | Path] = None,
        max_request_bytes: int = 1_000_000,
    ):
        if registry:
            self.registry = registry
        elif contract_dir:
            self.registry = ContractRegistry(contract_dir=str(contract_dir))
        else:
            self.registry = ContractRegistry()

        self.handlers = ScosMcpHandlers(self.registry)
        self.audit_log: list[McpAuditEvent] = []
        self.max_request_bytes = max_request_bytes

    def handle_request(self, req: Dict[str, Any], raw_payload_len: Optional[int] = None) -> Dict[str, Any]:
        """Process a single JSON-RPC 2.0 request."""
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if raw_payload_len and raw_payload_len > self.max_request_bytes:
            return self._error_response(req_id, -32600, f"Payload size exceeds limit of {self.max_request_bytes} bytes")

        if not method:
            return self._error_response(req_id, -32600, "Invalid Request: missing method")

        try:
            if method == "initialize":
                return self._success_response(req_id, {
                    "protocolVersion": self.PROTOCOL_VERSION,
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
                args = params.get("arguments", {})
                result = self.handlers.call_tool(name, args)

                # Record audit event
                audit = McpAuditEvent(
                    event_id=f"mcp-ev-{uuid.uuid4()}",
                    method="tools/call",
                    tool_name=name,
                    metric_id=args.get("metric_id"),
                    decision=result.get("decision"),
                    latency_ms=result.get("latency_ms", 0.0),
                )
                self.audit_log.append(audit)

                return self._success_response(req_id, {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]})

            elif method == "resources/list":
                res = [r.model_dump() for r in self.handlers.list_resources()]
                return self._success_response(req_id, {"resources": res})

            elif method == "resources/read":
                uri = params.get("uri")
                data = self.handlers.read_resource(uri)
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
                args = params.get("arguments", {})
                prompt_text = self.handlers.get_prompt(name, args)
                return self._success_response(req_id, {
                    "description": f"Prompt: {name}",
                    "messages": [
                        {"role": "user", "content": {"type": "text", "text": prompt_text}}
                    ]
                })

            elif method == "notifications/initialized":
                # No response required for notifications
                return {}

            else:
                return self._error_response(req_id, -32601, f"Method not found: '{method}'")

        except Exception as e:
            logger.exception(f"Error handling MCP method {method}")
            return self._error_response(req_id, -32603, f"Internal error: {str(e)}")

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
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = self.handle_request(req)
                if resp:  # Notifications return empty dict
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err = self._error_response(None, -32700, f"Parse error: {str(e)}")
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()
