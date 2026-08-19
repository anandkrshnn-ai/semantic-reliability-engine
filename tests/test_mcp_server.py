import json
import pytest

from semantic_reliability.compiler.schema import MetricDefinition, SemanticInvariants, PopulationInvariant
from semantic_reliability.firewall.engine import ContractRegistry
from semantic_reliability.mcp.models import CallerIdentity
from semantic_reliability.mcp.server import ScosMcpServer


@pytest.fixture
def mcp_server():
    registry = ContractRegistry()
    metric_finance = MetricDefinition(
        metric="net_revenue",
        owner="finance",
        grain="customer_month",
        sql="SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1",
        dialect="duckdb",
        metadata={"domain": "finance"},
        invariants=SemanticInvariants(
            population=PopulationInvariant(required_filters=["status = 'active'"])
        )
    )
    metric_ops = MetricDefinition(
        metric="delivery_time",
        owner="ops",
        grain="order_day",
        sql="SELECT order_id, AVG(delivery_days) AS delivery_time FROM orders GROUP BY 1",
        dialect="duckdb",
        metadata={"domain": "operations"},
    )
    registry.register(metric_finance)
    registry.register(metric_ops)
    return ScosMcpServer(registry=registry)


def test_mcp_initialize(mcp_server):
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"}
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
    caller = CallerIdentity(client_id="finance_bot", tenant_id="acme_corp")
    resp = mcp_server.handle_request(req, caller=caller)
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


def test_mcp_audit_hash_chain_and_signed_checkpoint(mcp_server):
    for i in range(3):
        mcp_server.handle_request({
            "jsonrpc": "2.0",
            "id": 100 + i,
            "method": "tools/call",
            "params": {
                "name": "scos_validate_sql",
                "arguments": {
                    "metric_id": "net_revenue",
                    "sql": f"SELECT customer_id, SUM(amount) FROM transactions WHERE status = 'active' /* {i} */ GROUP BY 1",
                }
            }
        })

    assert len(mcp_server.audit_log) == 3
    # 1. Verify tamper-evident hash chain
    assert mcp_server.verify_audit_chain() is True

    # 2. Create signed checkpoint
    cp = mcp_server.create_checkpoint()
    assert cp.sequence_end == 3
    assert cp.last_event_hash == mcp_server.audit_log[-1].event_hash
    assert len(cp.checkpoint_signature) == 64

    # 3. Verify checkpoint signature
    assert mcp_server.verify_checkpoint(cp) is True


def test_mcp_domain_authorization_scoping():
    registry = ContractRegistry()
    registry.register(MetricDefinition(
        metric="net_revenue", owner="finance", grain="day", sql="SELECT 1", metadata={"domain": "finance"}
    ))
    registry.register(MetricDefinition(
        metric="patient_vitals", owner="health", grain="day", sql="SELECT 1", metadata={"domain": "healthcare"}
    ))

    scoped_server = ScosMcpServer(registry=registry, allowed_domains=["finance"])

    # 1. List metrics should only return finance
    resp = scoped_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "scos_list_metrics", "arguments": {}}})
    data = json.loads(resp["result"]["content"][0]["text"])
    metric_ids = [m["metric_id"] for m in data["metrics"]]
    assert "net_revenue" in metric_ids
    assert "patient_vitals" not in metric_ids

    # 2. Get contract for unauthorized domain should be denied
    resp_get = scoped_server.handle_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "scos_get_contract", "arguments": {"metric_id": "patient_vitals"}}
    })
    data_get = json.loads(resp_get["result"]["content"][0]["text"])
    assert "Access denied" in data_get["error"]


def test_mcp_json_rpc_error_codes(mcp_server):
    # -32600: Invalid Request
    resp_inv = mcp_server.handle_request("not_a_json_dict")
    assert resp_inv["error"]["code"] == -32600

    # -32601: Method not found
    resp_meth = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "unknown_rpc"})
    assert resp_meth["error"]["code"] == -32601

    # -32602: Invalid params (missing tool name)
    resp_params = mcp_server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {}})
    assert resp_params["error"]["code"] == -32602

    # Malformed SQL returns structured failure
    resp_sql = mcp_server.handle_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "scos_validate_sql",
            "arguments": {"metric_id": "net_revenue", "sql": "INVALID SQL ;;;;"}
        }
    })
    data_sql = json.loads(resp_sql["result"]["content"][0]["text"])
    assert data_sql["compliant"] is False
    assert data_sql["decision"] == "DENY"


def test_mcp_ast_complexity_and_deep_nesting(mcp_server):
    # 1. Deeply nested Boolean expressions (should parse and validate correctly)
    nested_where = " AND ".join([f"x{i} = {i}" for i in range(10)])
    complex_sql = f"SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' AND ({nested_where}) GROUP BY 1"
    resp_comp = mcp_server.handle_request({
        "jsonrpc": "2.0",
        "id": 50,
        "method": "tools/call",
        "params": {
            "name": "scos_validate_sql",
            "arguments": {"metric_id": "net_revenue", "sql": complex_sql}
        }
    })
    data_comp = json.loads(resp_comp["result"]["content"][0]["text"])
    assert data_comp["compliant"] is True
    assert data_comp["decision"] == "ALLOW"

    # 2. Massive AST nodes exceeding MAX_AST_NODES limit (500)
    massive_predicates = " OR ".join([f"col_{i} = 'value_{i}'" for i in range(300)])
    massive_sql = f"SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' AND ({massive_predicates}) GROUP BY 1"
    resp_massive = mcp_server.handle_request({
        "jsonrpc": "2.0",
        "id": 51,
        "method": "tools/call",
        "params": {
            "name": "scos_validate_sql",
            "arguments": {"metric_id": "net_revenue", "sql": massive_sql}
        }
    })
    data_massive = json.loads(resp_massive["result"]["content"][0]["text"])
    assert data_massive["decision"] == "DENY"
    assert data_massive["violations"][0]["rule"] == "complexity_limit"


def test_scos_registry_and_security(tmp_path):
    from semantic_reliability.mcp.security import hash_sql, enforce_limits
    from semantic_reliability.mcp.registry import SCOSRegistry

    # 1. Test hash_sql
    h = hash_sql("SELECT * FROM transactions")
    assert len(h) == 64

    # 2. Test enforce_limits
    enforce_limits({"sql": "SELECT 1", "key": "val"})
    with pytest.raises(ValueError) as exc_sql:
        enforce_limits({"sql": "x" * 60_000})
    assert "exceeds limit" in str(exc_sql.value)

    # 3. Test SCOSRegistry URN and URI resolution
    c_yaml = tmp_path / "net_revenue.yaml"
    c_yaml.write_text("""
metric: net_revenue
owner: finance
grain: customer_month
sql: "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions WHERE status = 'active' GROUP BY 1"
metadata:
  domain: finance
""", encoding="utf-8")

    registry = SCOSRegistry(tmp_path)
    metrics = registry.list_metrics()
    assert "urn:scos:finance:net_revenue" in metrics

    contract = registry.get_contract("urn:scos:finance:net_revenue")
    assert contract.metric == "net_revenue"

    # Test URI resolution
    data = registry.resolve_uri("scos://contracts/finance/net_revenue/1.0.0")
    assert data["metric"] == "net_revenue"
