# 🏛️ Enterprise Architecture & CISO Governance Whitepaper
**Semantic Reliability Engine (SRE) & Semantic Contract Object Standard (SCOS)**  
**Document Version:** `1.0.0-PROD-SPEC`  
**Classification:** Technical Whitepaper / Architecture & Evaluation Reference  
**Protocol References:** `SCOS v1.0.0`, `Model Context Protocol (MCP) Draft 2024-11-05`, `SARIF 2.1.0`

---

## 1. Executive Summary

### 1.1 The Core Problem
Enterprise deployments of Text-to-SQL agents and automated analytical assistants face a fundamental reliability hazard: **an AI-generated analytical query may execute with 100% syntactic and database success while violating critical business-semantic contracts.**

Traditional database testing tools (such as standard schema linters, unit tests, and structural dbt checks) validate column existence, uniqueness, and non-null constraints, but cannot verify whether:
- Revenue queries deduct active discounts and refunds.
- Cohort retention queries apply mandatory customer activity filters (`status = 'active'`).
- Time-series aggregations respect the correct reporting grain.

When analytical agents operate without deterministic semantic boundaries, organizations risk silent metric drift, regulatory non-compliance, and flawed executive decisions.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      THE SILENT SEMANTIC FAILURE GAP                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  AI Agent Prompt: "Show net revenue for Q3 by customer"                     │
│                                                                             │
│  Candidate SQL:                                                             │
│    SELECT customer_id, SUM(amount) AS net_revenue                           │
│    FROM transactions                                                        │
│    GROUP BY 1;                                                              │
│                                                                             │
│  Database Execution Result:  ✅ SUCCESS (Status Code 0, Rows Returned)       │
│  Standard Data Quality Tests: ✅ PASS (Non-null, valid types)                │
│  Business Semantic Contract: ❌ FATAL VIOLATION (Missing status='active'     │
│                                                   filter & discount deduct) │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 The SRE Architecture
The **Semantic Reliability Engine (SRE)** provides a deterministic control plane that decouples business logic from model training. SRE introduces:
1. **Declarative Metric Contracts (`SCOS v1.0.0`):** Machine-readable YAML/JSON specifications defining canonical SQL, population filters, deduction rules, and reporting grains.
2. **Deterministic AST Validation:** Abstract Syntax Tree inspection (`sqlglot`) that statically checks candidate SQL against invariant rules prior to execution.
3. **Enterprise CI/CD Semantic Gate:** Native dbt manifest resolvers and BigQuery dry-run adapters for pull-request policy enforcement and SARIF 2.1.0 reporting.
4. **Read-Only MCP Server:** A Model Context Protocol interface exposing versioned contract discovery, pre-generation guidance, and structured violation diagnostics without warehouse execution privileges.
5. **Tamper-Evident Auditability:** Hash-chained audit event records anchored by periodic signed checkpoints.
6. **Scientific Agent Evaluation Harness:** A deterministic trajectory replay and scoring harness measuring Semantic Lift and Net Governance Benefit across paired blind vs. governed scenarios.

---

## 2. End-to-End System Architecture

```
                                  AI AGENT / LLM LOOP
                                          │
                        ┌─────────────────┴─────────────────┐
                        │ Pre-generation Metric Discovery   │
                        │ scos_list_metrics / get_contract  │
                        └─────────────────┬─────────────────┘
                                          ▼
                         ┌─────────────────────────────────┐
                         │      SCOS Read-Only MCP Server   │
                         │      (JSON-RPC 2.0 / Stdio)     │
                         └────────────────┬────────────────┘
                                          │
                        ┌─────────────────┴─────────────────┐
                        │ Pre-execution Invariant Check     │
                        │ scos_validate_sql                 │
                        └─────────────────┬─────────────────┘
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SRE SEMANTIC CONTROL PLANE                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────────────┐   ┌──────────────────────┐   ┌─────────────────────┐  │
│  │ SCOS Contract        │   │ AST Invariant Engine │   │ Reality Probes      │  │
│  │ Registry             ├──►│ (Static AST Analysis)├──►│ (Statistical Drift) │  │
│  └──────────────────────┘   └──────────┬───────────┘   └─────────────────────┘  │
│                                        │                                        │
│                                        ▼                                        │
│                             ┌──────────────────────┐                            │
│                             │ Policy & Decision    │                            │
│                             │ Engine (ALLOW/DENY)  │                            │
│                             └──────────┬───────────┘                            │
│                                        │                                        │
└────────────────────────────────────────┼────────────────────────────────────────┘
                                         │
                    ┌────────────────────┴────────────────────┐
                    ▼                                         ▼
      ┌───────────────────────────┐             ┌───────────────────────────┐
      │   CI/CD Pull Request Gate │             │ Tamper-Evident Audit Log  │
      │   (dbt / BigQuery Dry-Run)│             │ (Hash Chains & Checkpoints│
      │   SARIF 2.1.0 Alerting    │             │  Key-Signed Evidence)     │
      └───────────────────────────┘             └───────────────────────────┘
```

### 2.1 Architectural Components

#### A. SCOS Contract Registry (`semantic_reliability/compiler/`)
- Ingests versioned metric specifications (`spec/scos-v1.schema.json`).
- Resolves metric identifiers via uniform resource names (`urn:scos:{domain}:{metric}`).
- Enforces immutability of contract definitions at runtime.

#### B. AST Invariant Validator (`semantic_reliability/compiler/contracts.py`)
- Translates declared contract invariants into AST predicate trees.
- Validates:
  - **Population Invariants:** Required `WHERE` and `HAVING` filters (e.g., `status = 'active'`).
  - **Grain Invariants:** Enforced grouping keys (e.g., `GROUP BY customer_id, trans_date`).
  - **Arithmetic Invariants:** Required negative component deductions (e.g., `amount - refund_amount`).
- Operates in $O(\text{AST Nodes})$ time with strict complexity ceilings ($<500$ nodes).

#### C. BigQuery Dry-Run & dbt PR Gate (`semantic_reliability/adapters/`)
- Integrates into enterprise CI/CD pipelines via GitHub Actions (`.github/workflows/sre-dbt-semantic-gate.yml`).
- Resolves compiled SQL models directly from dbt `manifest.json`.
- Uses BigQuery `dry_run=True` to compute estimated bytes processed ($6.25/TiB list-price policy) and syntax validity without warehouse execution costs.
- Generates standard SARIF 2.1.0 reports for automated GitHub Pull Request security reviews.

#### D. Read-Only SCOS MCP Server (`semantic_reliability/mcp/`)
- Exposes tools (`scos_list_metrics`, `scos_get_contract`, `scos_validate_sql`, `scos_explain_violation`, `scos_get_probe_status`).
- Exposes resources (`scos://contracts/{domain}/{metric}/{version}`).
- Exposes invariant-grounded repair prompts (`scos_repair_contract_violation`).
- **Security Invariant:** Unconditionally returns `execution_performed: false`.

#### E. Tamper-Evident Audit Trail (`semantic_reliability/mcp/server.py`)
- Every tool invocation emits an audit record chained cryptographically:
  $$\text{event\_hash}_i = \text{SHA256}(\text{event\_hash}_{i-1} + \text{canonical\_json}(\text{event}_i))$$
- Periodic `AuditCheckpoint` records sign the chain head using a designated key identifier (`key_id`).

#### F. Deterministic Benchmark & Replay Harness (`semantic_reliability/benchmark/`)
- Evaluates analytical agents across 4 scenario classes: `CLEAR_CONTRACT`, `AMBIGUOUS_METRIC`, `MISSING_CONTRACT`, and `CONTRACT_CONFLICT`.
- Compares generated SQL against an in-memory DuckDB Oracle using order-insensitive, floating-point tolerant ($10^{-4}$) matrix comparisons.
- Replays historic JSONL trajectories to test for regression against modified SCOS contracts.

---

## 3. Threat Model & Security Architecture (STRIDE)

| Threat Category | Potential Attack Vector | SRE Defense & Mitigation |
| :--- | :--- | :--- |
| **Spoofing** | Rogue agent masquerading as an authorized data consumer | MCP transport binds requests to authenticated `CallerIdentity(client_id, tenant_id, allowed_domains)`. Unauthenticated remote callers are denied. |
| **Tampering** | Malicious alteration of metric definitions or invariant rules | SCOS Contract Registry is read-only at runtime; no write/mutation tools exist in MCP capabilities. |
| **Repudiation** | Agent or developer disputing that non-compliant SQL was generated | Every validation request produces a hash-chained audit event (`sql_sha256`, timestamp, sequence number, decision) anchored by signed checkpoints. |
| **Information Disclosure** | Leakage of proprietary database literals or PII through logs | Raw query strings are redacted from logs and trajectory exports. Only SHA-256 digests (`sql_sha256`) and sanitized metadata are preserved. |
| **Denial of Service** | Deeply nested recursive AST payloads or multi-megabyte queries | Hard request ceilings (`100KB`), SQL length limits (`50KB`), AST node ceilings (`500 nodes`), and non-SELECT statement denial (`DENY`). |
| **Elevation of Privilege** | SQL injection attempts inside MCP tool arguments | Candidate SQL is parsed via AST lexers (`sqlglot`) strictly for invariant matching; SQL strings are never interpolated or executed on live data warehouses. |
| **Oracle Contamination** | Benchmark oracle grading based on flawed golden SQL | `OracleValidator.validate_oracle()` statically proves that Golden SQL satisfies all SCOS contract invariants and matches fixture fingerprints before grading. |
| **Cross-Tenant Leakage** | Tenant A attempting to inspect Tenant B's financial metric contracts | Strict domain scoping filters (`allowed_domains`) reject out-of-scope metric queries with authorization errors without leaking metric existence. |

---

## 4. Evidence & Cryptographic Verification Model

To ensure transparency and compliance for internal audit and SOC 2 / ISO 27001 readiness, every SRE evaluation produces a multi-layered evidence artifact:

```json
{
  "event_id": "mcp-ev-8f7e2a1b-3c4d-5e6f",
  "sequence_num": 42,
  "timestamp_utc": 1771473600.0,
  "client_id": "finance_analyst_agent",
  "tenant_id": "enterprise_corp",
  "domain": "finance",
  "metric_id": "net_revenue",
  "contract_version": "1.0.0",
  "sql_sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
  "decision": "ALLOW",
  "violations": [],
  "execution_performed": false,
  "key_id": "sre-audit-key-2026-01",
  "previous_event_hash": "a1b2c3d4e5f6...",
  "event_hash": "e5f6g7h8i9j0..."
}
```

### Chain-of-Custody Verification
External compliance auditors verify trace integrity by running `server.verify_audit_chain()`, which checks that:
1. Every event correctly references the SHA-256 hash of its immediate predecessor.
2. The sequence numbers are monotonically increasing without gaps.
3. The latest event hash matches the cryptographic signature of the periodic `AuditCheckpoint`.

---

## 5. Agent Benchmark Methodology & Governance Metrics

SRE evaluates Text-to-SQL agents using a controlled paired protocol:

```
                       BENCHMARK SCENARIO (PROMPT + SCHEMA)
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 ▼                                           ▼
      BLIND AGENT CONDITION                      GOVERNED AGENT CONDITION
   (LLM without MCP access)                     (LLM with Read-Only MCP)
                 │                                           │
                 ▼                                           ▼
          Generated SQL                               Generated SQL
                 │                                           │
                 └─────────────────────┬─────────────────────┘
                                       ▼
                       DUCKDB ORACLE & INVARIANT EVALUATOR
                                       │
                                       ▼
                    MULTI-DIMENSIONAL GOVERNANCE SCORECARD
```

### 5.1 Scenario Taxonomy
- **`CLEAR_CONTRACT`**: Explicit metric query with a published SCOS contract. (Expected: `PRODUCE_SQL`).
- **`AMBIGUOUS_METRIC`**: Under-specified prompt with multiple interpretations. (Expected: `ASK_CLARIFICATION` or `REQUIRE_REVIEW`).
- **`MISSING_CONTRACT`**: Metric undefined in the registry. (Expected: `ABSTAIN`).
- **`CONTRACT_CONFLICT`**: Query intent contradicts declared metric invariants. (Expected: `ABSTAIN` or `REQUIRE_REVIEW`).

### 5.2 Scoring Formulation
1. **Unsafe Query Rate ($UQR$):**
   $$UQR = \frac{\text{Queries Executing Successfully but Violating Semantic Contracts}}{\text{Total Executable Queries}}$$
2. **Semantic Lift ($\Delta_{\text{sem}}$):**
   $$\Delta_{\text{sem}} = \text{Compliance}_{\text{governed}} - \text{Compliance}_{\text{blind}}$$
3. **Net Governance Benefit ($NGB$):**
   $$NGB = \Delta \text{Correctness} - \lambda_{\text{lat}}\Delta \text{Latency} - \lambda_{\text{cost}}\Delta \text{Cost} - \lambda_{\text{abs}}\Delta \text{Abstain}$$

---

## 6. Limitations & Methodological Constraints

To maintain scientific and operational integrity, enterprise deployers must note:

1. **Contract Completeness:** SRE validates candidate SQL strictly against declared SCOS invariants. It does not provide universal proof of query intent if the underlying contract is under-specified.
2. **Fixture Equivalence vs. Global Equivalence:** Result matching on local test fixtures demonstrates empirical agreement, not formal mathematical equivalence across all possible warehouse states.
3. **Statistical Probes:** Reality probes provide statistical distribution drift signals; they do not replace root-cause pipeline debugging.
4. **Audit Scope:** Hash-chained audit events provide tamper-evidence within the preserved event sequence; complete non-repudiation requires external durable anchoring and trusted key management.
5. **Model Variance:** Model outputs are provider- and version-specific; evaluations should be repeated across multiple rollouts ($N \ge 3$) to measure dispersion.

---

## 7. Operational Deployment & Integration Checklist

- [x] **Compile Contracts:** `sre compile --contract contracts/finance/net_revenue.yaml`
- [x] **Verify CI/CD Gate:** Add `.github/workflows/sre-dbt-semantic-gate.yml` to repository.
- [x] **Launch MCP Server:** `sre mcp-serve --contracts ./contracts`
- [x] **Run Regression Replay:** `sre benchmark-replay --trajectories runs/prod_trajectories.jsonl --contracts ./contracts`
- [x] **Execute Benchmark Evaluation:** `sre benchmark-live --contracts ./contracts --output scorecard.json`
