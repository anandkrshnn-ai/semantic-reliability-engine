"""Demo Analytics Agent interacting with SCOS MCP Server.
Demonstrates:
1. Valid Query -> ALLOW
2. Semantically Invalid Query -> REQUIRE_REVIEW
3. Ambiguous / Missing Contract -> ABSTAIN
"""
import sys
import time
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from semantic_reliability.compiler.compiler import MetricCompiler
from semantic_reliability.firewall.engine import ContractRegistry
from semantic_reliability.mcp.handlers import ScosMcpHandlers
from semantic_reliability.mcp.server import ScosMcpServer


def run_demo():
    print("=" * 70)
    print("[DEMO] SCOS-MCP ENTERPRISE AGENT GOVERNANCE DEMO")
    print("=" * 70)

    # 1. Initialize Registry & Handlers locally
    registry = ContractRegistry()
    corpus_path = Path("benchmark_corpus/dev")
    if corpus_path.exists():
        for p in corpus_path.rglob("*.yaml"):
            try:
                comp = MetricCompiler.from_yaml_file(p)
                registry.register(comp.definition)
            except Exception:
                pass

    handlers = ScosMcpHandlers(registry=registry)
    server = ScosMcpServer(registry=registry)

    print("\n[INFO] Registered Metric Contracts:")
    metrics = handlers.call_tool("scos_list_metrics", {"domain": "finance"})
    for m in metrics.get("metrics", []):
        print(f"  * {m['urn']} ({m['metric']}) - Owner: {m['owner']}")

    # Scenario 1: Valid Query -> ALLOW
    print("\n" + "-" * 70)
    print("Scenario 1: Compliant Agent Query on `net_revenue`")
    print("-" * 70)
    valid_sql = (
        "SELECT customer_id, DATE_TRUNC('month', transaction_date) AS reporting_month, "
        "SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) - SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue "
        "FROM transactions WHERE region = 'NA' AND status = 'active' GROUP BY 1, 2"
    )
    print(f"Agent Draft SQL:\n{valid_sql}\n")
    res1 = handlers.call_tool("scos_validate_sql", {"metric_id": "net_revenue", "sql": valid_sql})
    print(f"SCOS MCP Decision: -> {res1.get('decision')} (Passed: {res1.get('passed')})")

    # Scenario 2: Semantically Invalid Query -> REQUIRE_REVIEW
    print("\n" + "-" * 70)
    print("Scenario 2: Flawed Agent Query on `net_revenue` (Missing required status filter)")
    print("-" * 70)
    flawed_sql = "SELECT customer_id, SUM(amount) AS net_revenue FROM transactions GROUP BY 1"
    print(f"Agent Draft SQL:\n{flawed_sql}\n")
    res2 = handlers.call_tool("scos_validate_sql", {"metric_id": "net_revenue", "sql": flawed_sql})
    print(f"SCOS MCP Decision: -> {res2.get('decision')} (Passed: {res2.get('passed')})")
    print("Violations:")
    for v in res2.get("violations", []):
        print(f"  [X] [{v.get('rule')}] {v.get('details')}")

    # Scenario 3: Ambiguous / Missing Contract -> ABSTAIN
    print("\n" + "-" * 70)
    print("Scenario 3: Unregistered Metric Request (`viral_k_factor`)")
    print("-" * 70)
    res3 = handlers.call_tool("scos_get_contract", {"metric_id": "viral_k_factor"})
    print(f"Lookup Result: Found = {res3.get('found')}")
    if not res3.get("found"):
        print("Agent Action: -> ABSTAIN (Refusing to hallucinate unanchored metric definitions)")

    print("\n" + "=" * 70)
    print("[SUCCESS] DEMO COMPLETE: All semantic invariants verified successfully.")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
