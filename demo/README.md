# SCOS-MCP Local Docker Demo Environment

This directory provides a lightweight, local demonstration of the **Semantic Contract Open Standard (SCOS) Model Context Protocol (MCP) Server** interacting with an analytical AI agent.

> **Security Note:** This Docker environment is designed as a **local evaluation and research demonstration**, not a full enterprise deployment. In enterprise deployments, SCOS MCP servers are deployed with TLS termination, enterprise identity management (mTLS / OAuth2), and KMS-anchored audit logging.

---

## 🎯 What the Demo Shows

1. **Scenario 1 (Valid Query $\rightarrow$ `ALLOW`):** The agent consults the SCOS contract for `net_revenue` and constructs SQL that satisfies all population, grain, and aggregation invariants. The SCOS MCP server validates the AST and returns `ALLOW`.
2. **Scenario 2 (Semantically Flawed Query $\rightarrow$ `REQUIRE_REVIEW`):** The agent generates a query that executes cleanly on SQL engines but omits the required `status = 'active'` and `region = 'NA'` filters. The SCOS MCP validator intercepts the query, returns `REQUIRE_REVIEW`, and outputs exact structural violations.
3. **Scenario 3 (Missing / Ambiguous Contract $\rightarrow$ `ABSTAIN`):** The user requests a metric with no published contract (`viral_k_factor`). The agent queries `scos_get_contract`, discovers no definition exists, and triggers an explicit `ABSTAIN` rather than hallucinating custom business logic.

---

## 📋 Terminal Output Transcript

```text
======================================================================
[DEMO] SCOS-MCP ENTERPRISE AGENT GOVERNANCE DEMO
======================================================================

[INFO] Registered Metric Contracts:
  * urn:scos:finance:net_revenue (net_revenue) - Owner: finance

----------------------------------------------------------------------
Scenario 1: Compliant Agent Query on `net_revenue`
----------------------------------------------------------------------
Agent Draft SQL:
SELECT customer_id, DATE_TRUNC('month', transaction_date) AS reporting_month, SUM(CASE WHEN type = 'invoice' THEN amount ELSE 0 END) - SUM(CASE WHEN type = 'refund' THEN amount ELSE 0 END) AS net_revenue FROM transactions WHERE region = 'NA' AND status = 'active' GROUP BY 1, 2

SCOS MCP Decision: -> ALLOW (Passed: None)

----------------------------------------------------------------------
Scenario 2: Flawed Agent Query on `net_revenue` (Missing required status filter)
----------------------------------------------------------------------
Agent Draft SQL:
SELECT customer_id, SUM(amount) AS net_revenue FROM transactions GROUP BY 1

SCOS MCP Decision: -> REQUIRE_REVIEW (Passed: None)
Violations:
  [X] [Required filter: `status = 'active'`] None
  [X] [Required filter: `region = 'NA'`] None
  [X] [Positive component `type = 'invoice'`] None
  [X] [Negative component `type = 'refund'`] None

----------------------------------------------------------------------
Scenario 3: Unregistered Metric Request (`viral_k_factor`)
----------------------------------------------------------------------
Lookup Result: Found = False
Agent Action: -> ABSTAIN (Refusing to hallucinate unanchored metric definitions)

======================================================================
[SUCCESS] DEMO COMPLETE: All semantic invariants verified successfully.
======================================================================
```

---

## 🚀 Running Locally with Python

```bash
# Run the demo directly
python demo/agent.py
```

---

## 🐳 Running with Docker Compose

```bash
# Build and run the hardened container stack
docker compose -f demo/docker-compose.yml up --build
```
