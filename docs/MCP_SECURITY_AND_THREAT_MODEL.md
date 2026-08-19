# 🛡️ SCOS MCP Server: Security Architecture & Threat Model
**Specification Version:** `scos-mcp-v1.1.0`  
**Protocol Compatibility:** `Model Context Protocol (MCP) Draft 2024-11-05`

---

## 1. Security Philosophy: Read-Only Semantic Guidance

The SCOS Model Context Protocol (MCP) Server is designed to solve the **"Liability & Hallucination Trap"** in enterprise Text-to-SQL workflows. When an AI agent generates SQL for business metrics, it must not blindly execute queries or guess business logic.

The SCOS MCP Server operates strictly as a **read-only semantic consultant**:
- **Zero Arbitrary Execution:** The server has no execution privileges on downstream data warehouses. `execution_performed` is unconditionally `false`.
- **Zero Silent Rewrites:** The server never mutates or "auto-fixes" SQL behind the scenes. It returns declarative violations and structured guidance, forcing the agent or human to generate compliant SQL.
- **Zero Direct Data Access:** The server returns metric schemas, invariant trees, and probe bounds—never raw row data or customer records.

---

## 2. Threat Model & Mitigations (STRIDE Matrix)

| Threat Category | Potential Attack Vector | SCOS MCP Defense & Mitigation |
| :--- | :--- | :--- |
| **Spoofing** | Unauthorized agent masquerading as a compliance service | Server presents signed SCOS protocol metadata (`serverInfo`, `protocolVersion: 2024-11-05`), binds requests to `CallerIdentity(client_id, tenant_id, allowed_domains)`. |
| **Tampering** | Attempting to alter metric definitions or bypass invariant rules | In-memory `ContractRegistry` is immutable at runtime. No `write`, `update`, or `patch` tools are exposed. |
| **Repudiation** | Agent claims an unverified SQL query was validated by SRE | Every interaction creates a **hash-chained tamper-evident audit event** anchored by periodic signed `AuditCheckpoint` records. |
| **Information Disclosure** | Leakage of PII or sensitive business literals in audit logs | Raw SQL literals and identifiers are hashed with SHA-256. Logs capture `sql_sha256`, `metric_id`, `decision`, and latency only. |
| **Denial of Service** | Agent sending recursive AST payloads or multi-megabyte queries | Hard request ceilings (`max_request_bytes = 1,000,000`), SQL length limits (`MAX_SQL_LENGTH = 50,000`), and AST node ceilings (`MAX_AST_NODES = 500`). |
| **Elevation of Privilege** | Agent attempting SQL injection through parameter values | SQL is parsed via AST lexers (`sqlglot`) strictly for invariant matching; SQL strings are never interpolated or executed on a live database. Multi-statement queries and DDL/DML are immediately rejected with `DENY`. |

---

## 3. Tool Surface & Permissions Policy

| Tool Name | Access Level | Description |
| :--- | :---: | :--- |
| `scos_list_metrics` | `READ_ONLY` | Discovers registered metric contracts filtered strictly by authorized domains. |
| `scos_get_contract` | `READ_ONLY` | Returns canonical ground-truth SQL and declared AST invariants for authorized domains. |
| `scos_validate_sql` | `READ_ONLY` | Validates SQL against declared invariants; returns `ALLOW` / `REQUIRE_REVIEW` / `DENY`. |
| `scos_explain_violation` | `READ_ONLY` | Provides remediation guidance explaining why an invariant failed without silent rewrites. |
| `scos_get_probe_status` | `READ_ONLY` | Returns statistical reality probe distribution limits and health status. |

---

## 4. Hash-Chained Tamper-Evident Audit Model

Every MCP interaction appends a cryptographically chained audit record:

```json
{
  "event_id": "mcp-ev-8f7e2a1b-3c4d-5e6f",
  "sequence_num": 42,
  "timestamp_utc": 1771473600.0,
  "method": "tools/call",
  "tool_name": "scos_validate_sql",
  "metric_id": "net_revenue",
  "tenant_id": "acme_corp",
  "domain": "finance",
  "sql_sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
  "decision": "REQUIRE_REVIEW",
  "latency_ms": 3.42,
  "client_id": "finance_bot",
  "key_id": "sre-audit-key-2026-01",
  "previous_event_hash": "a1b2c3d4...",
  "event_hash": "e5f6g7h8..."
}
```

Periodic signed checkpoints anchor the chain state against an external signing key:
$$\text{checkpoint\_signature} = \text{SHA256}(\text{checkpoint\_id} : \text{sequence\_end} : \text{last\_event\_hash} : \text{timestamp} : \text{key\_id} : \text{secret})$$
