# SCOS-MCP Local Docker Demo Environment

This directory provides a lightweight, local demonstration of the **Semantic Contract Open Standard (SCOS) Model Context Protocol (MCP) Server** interacting with an analytical AI agent.

---

## 🎯 What the Demo Shows

1. **Scenario 1 (Valid Query $\rightarrow$ `ALLOW`):** The agent consults the SCOS contract for `net_revenue` and constructs SQL that satisfies all population, grain, and aggregation invariants. The SCOS MCP server validates the AST and returns `ALLOW`.
2. **Scenario 2 (Semantically Flawed Query $\rightarrow$ `REQUIRE_REVIEW`):** The agent generates a query that executes cleanly on SQL engines but omits the required `status = 'active'` and `region = 'NA'` filters. The SCOS MCP validator intercepts the query, returns `REQUIRE_REVIEW`, and outputs exact structural violations.
3. **Scenario 3 (Missing / Ambiguous Contract $\rightarrow$ `ABSTAIN`):** The user requests a metric with no published contract (`viral_k_factor`). The agent queries `scos_get_contract`, discovers no definition exists, and triggers an explicit `ABSTAIN` rather than hallucinating custom business logic.

---

## 🚀 Running Locally with Python

```bash
# Run the demo directly
python demo/agent.py
```

---

## 🐳 Running with Docker Compose

```bash
# Build and run the demo container stack
docker compose -f demo/docker-compose.yml up --build
```
