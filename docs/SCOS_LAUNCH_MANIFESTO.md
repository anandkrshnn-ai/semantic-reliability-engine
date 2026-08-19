# The Semantic Contract Open Standard (SCOS) Manifesto

> **AI-generated SQL can execute successfully and still violate business meaning. SCOS makes business semantics explicit, testable, and discoverable by agents.**

---

## 1. The Silent Semantic Failure Problem

In the modern enterprise, Large Language Model (LLM) agents are writing queries against cloud data warehouses at superhuman speed.

Standard benchmarks celebrate high execution rates and syntactic parsing accuracy. However, in production analytics environments, data engineering teams face **the silent semantic failure gap**:

A query can:
- Parse into a valid SQL abstract syntax tree (AST) with zero syntax errors;
- Execute across Snowflake, BigQuery, Databricks, or DuckDB in milliseconds;
- Return formatted tables and numbers with zero runtime exceptions;

...and yet be **fundamentally wrong about the underlying business metric**.

When an agent calculates *Net Revenue* without deducting customer refunds, when it measures *Monthly Active Users* without filtering out automated bot scripts, or when it aggregates *Churn Rate* over trial accounts, **the database engine does not throw an error**. The query succeeds, the dashboard updates, and business decisions are made based on flawed numbers.

Traditional data observability tools check table schemas and null counts; they do not evaluate whether the analytical logic inside an autonomous agent's query adheres to organizational definitions.

---

## 2. How SCOS Differs from Traditional Data Contracts

Existing data contract standards (such as ODCS or table-level data contracts) focus primarily on **dataset schemas, types, and producer/consumer SLAs**.

**SCOS is designed specifically for analytical meaning and query-level semantic logic:**

| Dimension | Traditional Data Contracts | SCOS Semantic Contracts |
| :--- | :--- | :--- |
| **Primary Scope** | Table schemas, column types, SLA metadata | Query-level mathematical & population invariants |
| **Enforcement Point** | Data producers / ingestion pipelines | Agent reasoning loop & analytical CI/CD gates |
| **Validation Mechanism** | Schema comparison & column assertions | Multi-dialect AST normalization & invariant parsing |
| **Agent Interface** | Static schema documentation | Read-only Model Context Protocol (MCP) server |
| **Evaluation Model** | Row-count & null checks on tables | Denominator-precise chaos mutation scoring |

---

## 3. The SCOS Architecture

An SCOS contract binds analytical logic to machine-readable rules:
- **Grain Invariants:** Required group-by dimensions.
- **Population Invariants:** Mandatory WHERE-clause filters (e.g., `status = 'active'`, `region = 'NA'`).
- **Aggregation Invariants:** Explicit positive and negative formula components (e.g., invoices minus refunds).
- **Join Invariants:** Permitted table relationship paths to prevent fan-out multiplication.
- **Reality Probes:** Statistical telemetry signals that monitor data health for population drift and null anomalies.

---

## 4. Agent Governance via Read-Only MCP

Through the **Model Context Protocol (MCP)**, SCOS provides an interactive consultation layer for AI agents:

```text
User Prompt
    │
    ▼
AI Agent (Claude / GPT / Llama)
    │
    ├── (1) scos_get_contract("net_revenue") ──► Discovers mandatory filters
    ├── (2) Drafts Candidate SQL
    └── (3) scos_validate_sql(draft_sql)    ──► AST Normalization & Verification
            │
            ├── Compliant?  ──► ALLOW ──► Executes on Warehouse
            ├── Violations? ──► REQUIRE_REVIEW ──► Agent Self-Corrects Draft
            └── Ambiguous?  ──► ABSTAIN ──► Requests Human Clarification
```

### Security & Operational Boundaries
- **Strictly Read-Only:** The SCOS MCP server executes zero warehouse queries and cannot mutate contracts.
- **Tamper-Evident Audit Trails:** Every tool invocation is recorded in a SHA-256 cryptographic hash-chain.
- **Zero-Compute Trajectory Replay:** Historical agent trajectories can be replayed against updated contracts in seconds without re-running LLMs or scanning warehouses.

---

## 5. An Open Standard for AI-Assisted Analytics

We believe semantic definitions should be open, declarative, and discoverable. SCOS bridges the gap between data engineering definitions and autonomous AI systems.

- **Specification:** [`spec/SCOS_V1_SPECIFICATION.md`](../spec/SCOS_V1_SPECIFICATION.md)
- **JSON Schema:** [`spec/scos-v1.schema.json`](../spec/scos-v1.schema.json)
- **Reference Implementation:** [github.com/semantic-reliability-engine/semantic-reliability-engine](https://github.com/semantic-reliability-engine/semantic-reliability-engine)
