import json
import pytest

from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant
from semantic_reliability.firewall.engine import ContractRegistry
from semantic_reliability.mcp.server import ScosMcpServer


@pytest.fixture
def mcp_server():
    registry = ContractRegistry()
    metric_def = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1",
        dialect="duckdb",
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"])
        )
    )
    registry.register(metric_def)
    return ScosMcpServer(registry=registry)


def test_mcp_initialize(mcp_server):
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    resp = mcp_server.handle_request(req)
    assert resp["id"] == 1
    assert "result" in resp
    assert resp["result"]["serverInfo"]["name"] == "scos-mcp-server"
    assert "tools" in resp["result"]["capabilities"]


def test_mcp_list_tools(mcp_server):
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    resp = mcp_server.handle_request(req)
    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "scos_list_metrics" in tool_names
    assert "scos_get_contract" in tool_names
    assert "scos_validate_sql" in tool_names
    assert "scos_explain_violation" in tool_names
    assert "scos_get_probe_status" in tool_names


def test_mcp_call_validate_sql_compliant(mcp_server):
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "scos_validate_sql",
            "arguments": {
                "metric_id": "net_revenue",
                "sql": "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1",
                "dialect": "duckdb"
            }
        }
    }
    resp = mcp_server.handle_request(req)
    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["compliant"] is True
    assert content["decision"] == "ALLOW"
    assert content["execution_performed"] is False
    assert "sql_sha256" in content


def test_mcp_call_validate_sql_violation(mcp_server):
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "scos_validate_sql",
            "arguments": {
                "metric_id": "net_revenue",
                "sql": "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions GROUP BY 1",
                "dialect": "duckdb"
            }
        }
    }
    resp = mcp_server.handle_request(req)
    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["compliant"] is False
    assert content["decision"] == "REQUIRE_REVIEW"
    assert len(content["violations"]) > 0


def test_mcp_resources(mcp_server):
    req_list = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "resources/list",
        "params": {}
    }
    resp_list = mcp_server.handle_request(req_list)
    uris = [r["uri"] for r in resp_list["result"]["resources"]]
    assert "scos://policies/semantic-gate/1.0" in uris

    # Read policy resource
    req_read = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "resources/read",
        "params": {"uri": "scos://policies/semantic-gate/1.0"}
    }
    resp_read = mcp_server.handle_request(req_read)
    policy_data = json.loads(resp_read["result"]["contents"][0]["text"])
    assert policy_data["strict_mode_default"] is True


def test_mcp_prompts(mcp_server):
    req_list = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "prompts/list",
        "params": {}
    }
    resp_list = mcp_server.handle_request(req_list)
    prompts = resp_list["result"]["prompts"]
    p_names = [p["name"] for p in prompts]
    assert "scos_generate_sql_guidance" in p_names
    assert "scos_repair_contract_violation" in p_names

    # Get prompt
    req_get = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "prompts/get",
        "params": {
            "name": "scos_generate_sql_guidance",
            "arguments": {
                "metric_id": "net_revenue",
                "user_intent": "Calculate net revenue by customer"
            }
        }
    }
    resp_get = mcp_server.handle_request(req_get)
    msg_text = resp_get["result"]["messages"][0]["content"]["text"]
    assert "net_revenue" in msg_text
    assert "status = 'active'" in msg_text


def test_mcp_error_handling_and_limits(mcp_server):
    # 1. Unknown method
    req_unknown = {"jsonrpc": "2.0", "id": 9, "method": "unsupported/method"}
    resp_unknown = mcp_server.handle_request(req_unknown)
    assert resp_unknown["error"]["code"] == -32601

    # 2. Malformed SQL
    req_malformed = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "scos_validate_sql",
            "arguments": {
                "metric_id": "net_revenue",
                "sql": "SELECT FROM WHERE ;;; INVALID",
            }
        }
    }
    resp_malformed = mcp_server.handle_request(req_malformed)
    content = json.loads(resp_malformed["result"]["content"][0]["text"])
    assert content["compliant"] is False
    assert content["decision"] == "DENY"
    assert content["violations"][0]["rule"] == "syntax_error"

    # 3. Payload size limit
    req_large = {"jsonrpc": "2.0", "id": 11, "method": "initialize"}
    resp_large = mcp_server.handle_request(req_large, raw_payload_len=2_000_000)
    assert resp_large["error"]["code"] == -32600
    assert "Payload size exceeds limit" in resp_large["error"]["message"]

    # 4. Verify audit trail was recorded
    assert len(mcp_server.audit_log) > 0
    assert mcp_server.audit_log[-1].method == "tools/call"

