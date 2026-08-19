# The Semantic Contract Open Standard (SCOS) Manifesto

> **AI-generated SQL can be executable and still be semantically wrong. SCOS makes business meaning explicit, testable, and discoverable by agents.**

---

## 1. The Silent Semantic Failure Problem

In the modern enterprise, Large Language Model (LLM) agents are writing queries against massive cloud data warehouses at superhuman speed. 

Benchmarks celebrate high execution accuracy and syntactic exact-match scores. But in production, data teams and enterprise leaders face a far more dangerous phenomenon: **The Silent Semantic Failure Gap**.

A query can:
- Parse into a valid SQL abstract syntax tree (AST) with zero errors;
- Execute across Snowflake, BigQuery, Databricks, or DuckDB in milliseconds;
- Return formatted tables and numbers;

...and yet be **completely wrong about the business**.

When an agent calculates *Net Revenue* without deducting customer refunds, when it measures *Monthly Active Users* without filtering out automated bot scripts, or when it aggregates *Churn Rate* over trial accounts, **the database engine does not throw an error**. The query succeeds, the dashboard updates, and executives make six-figure decisions based on flawed numbers.

Traditional data observability linters check table schemas and null counts; they do not check whether the logic inside an autonomous agent's query matches the company's agreed-upon definitions.

---

## 2. What is SCOS?

The **Semantic Contract Open Standard (SCOS)** is an open, vendor-neutral specification for declaring business-semantic invariants directly in code.

An SCOS contract binds analytical logic to machine-readable rules:
- **Grain Invariants:** Required group-by dimensions.
- **Population Invariants:** Mandatory WHERE-clause filters (e.g., `status = 'active'`, `region = 'NA'`).
- **Aggregation Invariants:** Required positive and negative formula components (e.g., invoices minus refunds).
- **Join Invariants:** Permitted table relationship paths to prevent fan-out multiplication.
- **Reality Probes:** Automated statistical checks that detect when production data drifts away from real-world assumptions.

---

## 3. How Agents Use SCOS via MCP

Through the **Model Context Protocol (MCP)**, SCOS provides a read-only governance layer for AI agents:

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

The SCOS MCP Server:
- **Executes Zero Warehouse SQL:** Completely read-only with minimal attack surface.
- **Tamper-Evident Audit Trails:** Every tool invocation is recorded in a SHA-256 cryptographic hash-chain anchored by signed checkpoints.
- **Zero-Compute Trajectory Replay:** Historical agent runs can be replayed against updated contracts in seconds without spending inference or warehouse budget.

---

## 4. An Open Standard for the AI-Assisted Enterprise

We believe that semantic truth should not be locked inside proprietary black boxes. By making semantic contracts open, declarative, and discoverable, data engineering teams and AI systems can finally speak the exact same language.

Join the open standard:
- **Specification:** [`spec/SCOS_V1_SPECIFICATION.md`](../spec/SCOS_V1_SPECIFICATION.md)
- **JSON Schema:** [`spec/scos-v1.schema.json`](../spec/scos-v1.schema.json)
- **Reference Implementation:** [github.com/semantic-reliability-engine/semantic-reliability-engine](https://github.com/semantic-reliability-engine/semantic-reliability-engine)
