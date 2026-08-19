# Semantic Reliability Control Plane: Runtime Governance for AI-Generated Analytics

**Subtitle:** Contracts, mutation-calibrated evaluation, replay, and statistical signals for trustworthy analytical agents.  
**Document Version:** `1.0.0-GA`  
**Classification:** Technical Whitepaper & Architectural Specification  
**Author:** Anandakrishnan Damodaran & The Semantic Reliability Engineering Team  
**Date:** August 2026  

---

## 1. Executive Summary

Enterprise adoption of AI-generated analytics—spanning Text-to-SQL assistants, autonomous analytics agents, and BI copilots—is accelerating rapidly. However, organizations face a critical operational hazard:

> **AI-generated SQL can execute cleanly without database syntax errors, pass generic table-level data quality tests, and still produce mathematically invalid, business-distorted metrics.**

Traditional data quality testing tools (e.g. dbt schema tests, Great Expectations, Monte Carlo) evaluate syntactic validity, null boundaries, and uniqueness constraints. They are designed for batch pipeline health, not for verifying whether dynamic, agent-generated queries adhere to declared organizational business definitions.

The **Semantic Reliability Engine (SRE)** establishes an end-to-end, audit-first **Semantic Control Plane** that governs analytical queries across their entire lifecycle. SRE decouples query generation from query authorization:

```
[Agent / BI / Copilot]
         ↓
[1. Semantic Contract Layer]       → Declarative Metric Ground-Truth
         ↓
[2. Pre-Execution Firewall]        → Sub-millisecond ALLOW / AUDIT / REQUIRE_REVIEW / DENY
         ↓
[3. Warehouse Query Execution]     → Isolated Execution Gateway
         ↓
[4. Offline Replay & Mutation]     → Mutation-Calibrated Blind Spot Detection
         ↓
[5. Statistical Reality Probes]    → Empirical Drift & Attribute Decoupling Signals
         ↓
[6. Immutable Audit & Evidence]    → Provenance Logs for Compliance & Human-in-the-Loop Review
```

---

## 2. The Analytical Failure Model & Control Gaps

Modern data platforms suffer from distinct classes of failure, of which traditional data testing only observes the structural surface:

| Failure Class | Example Manifestation | Traditional Testing Detection | SRE Control Plane Mechanism |
| :--- | :--- | :---: | :--- |
| **Syntax Failure** | Invalid SQL keywords or unclosed parenthesis | ✅ 100% (DB Parser) | Static AST compilation check |
| **Schema Failure** | Column `mrr` renamed to `mrr_amount` | ✅ 100% (Warehouse Engine) | AST schema resolution |
| **Structural Failure** | Column contains unintended nulls or duplicates | ✅ High (dbt `not_null`, `unique`) | Generic structural assertions |
| **Semantic Failure** | Omitted `WHERE status = 'active'` filter | ❌ **0% (Silent False Green)** | **Pre-Execution Firewall (Contract Invariant Check)** |
| **Temporal Failure** | 7-day vs 30-day attribution window discrepancy | ❌ **0% (Silent False Green)** | **Temporal Invariant & Mutation Harness** |
| **Metric Formulation** | `SUM(amount)` replaced by `AVG(amount)` | ❌ **0% (Silent False Green)** | **Aggregation Invariant & Mutation Harness** |
| **Arithmetic Component** | Forgetting to subtract refunds/discounts | ❌ **0% (Silent False Green)** | **Negative Component Verification** |
| **Reality Shift (Drift)**| Source CRM changes `active` from Paid to Free Trial | ❌ **0% (Silent False Green)** | **Layered Statistical Reality Probes** |

---

## 3. Five-Layer Reference Architecture

```text
+-----------------------------------------------------------------------------------+
|                           AGENT / BI / CLIENT APPLICATION                         |
+-----------------------------------------------------------------------------------+
                                         │  POST /evaluate (SQL + Metric ID)
                                         ▼
+───────────────────────────────────────────────────────────────────────────────────+
| [LAYER 1] SEMANTIC CONTRACT REGISTRY                                              |
|  - Metric Population Invariants     - Reporting Grain Invariants                  |
|  - Aggregation Component Rules      - Unit & Currency Envelopes                   |
|  - Temporal Attribution Windows     - Layered Statistical Probe Baselines         |
+───────────────────────────────────────────────────────────────────────────────────+
                                         │
                                         ▼
+───────────────────────────────────────────────────────────────────────────────────+
| [LAYER 2] PRE-EXECUTION SEMANTIC FIREWALL (FastAPI Sidecar Proxy)                  |
|  - Multi-Dialect AST Parsing        - Commutative Boolean Normalization           |
|  - Rule Verification vs Contract    - Policy Engine (strict_mode: true/false)     |
|                                                                                   |
|  [DECISIONS]:                                                                     |
|    • ALLOW          → Compliant with all declared invariants                      |
|    • AUDIT          → Minor anomaly; allowed but tagged for offline review        |
|    • REQUIRE_REVIEW → Critical violation under non-strict policy; blocked pending |
|    • DENY           → Critical violation under strict policy; hard block          |
+───────────────────────────────────────────────────────────────────────────────────+
                                         │
                   ┌─────────────────────┴─────────────────────┐
                   ▼ [If Allowed]                              ▼ [Always Emitted]
+───────────────────────────────────────+   +───────────────────────────────────────+
| DATA WAREHOUSE / QUERY ENGINE         |   | [LAYER 5] IMMUTABLE AUDIT & EVIDENCE  |
| (Snowflake / BigQuery / DuckDB)       |   | - Trace ID, Agent ID, SQL Hash        |
| Executes authorized analytical query  |   | - Contract Version & Violations       |
| Returns verified metric results       |   | - Mutation Equivalent Mappings        |
+───────────────────────────────────────+   +───────────────────────────────────────+
                                                               │
                                                               ▼ Batch Ingest
+───────────────────────────────────────────────────────────────────────────────────+
| [LAYER 3] OFFLINE REPLAY & MUTATION HARNESS                                       |
|  - Consumes production audit logs for ALLOW / AUDIT queries                       |
|  - Replays SQL against historical DuckDB data partitions                          |
|  - Injects AST mutations (FILTER_DROP, BOUNDARY_SHIFT, AGGREGATION_SWAP)          |
|  - Identifies "Silent Survivors" (mutations causing variance with 0 contract hits)|
|  - Generates automated Pull Request patches with suggested YAML invariants        |
+───────────────────────────────────────────────────────────────────────────────────+
                                         │
                                         ▼
+───────────────────────────────────────────────────────────────────────────────────+
| [LAYER 4] LAYERED STATISTICAL PROBES (Data Reality Monitoring)                    |
|  - Population Stability: Monitored slice proportion vs baseline                   |
|  - Semantic Implication: P(Condition B | Condition A) conditional probability     |
|  - Null Rate Drift: Critical semantic column null monitoring                      |
|  - Outputs structured SemanticProbeAlerts with likely causes & required action    |
+───────────────────────────────────────────────────────────────────────────────────+
```

---

## 4. Benchmark Evidence & Denominator Mathematics

To validate that SRE’s contract and mutation assertions reliably distinguish valid semantic defects without false certainty, the platform was benchmarked across a 14-model dual-track corpus evaluated under **Scientific Validity Policy v1.0**.

### 4.1. Mathematical Accounting Invariants
To prevent score inflation and guarantee reproducibility, all evaluations enforce strict denominator accounting identities:

1. **Total Generated Mutations ($G$):**
   $$G = E + U + V$$
   *(Where $E$ = Equivalent on fixture, $U$ = Unexecutable runtime error, $V$ = Valid executable non-equivalent defects).*

2. **Valid Defect Decomposition ($V$):**
   $$V = D + S$$
   *(Where $D$ = Detected defects, $S$ = Surviving defects).*

3. **Effective Catch Score:**
   $$\text{CatchScore} = \begin{cases} 100 \times \frac{D}{V}, & V > 0 \\ \text{NOT\_APPLICABLE}, & V = 0 \end{cases}$$

### 4.2. Dual-Track Benchmark Results

| Benchmark Track | Models | Valid Defects ($V$) | Generic Constraint Catch (Pooled) | Semantic Suite Catch (Pooled) | Macro-Average Catch Rate | Certified Conclusive Models |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Development Track** | 8 | 25 | **16.0%** (4 / 25)<br><sub>95% CI: [5.3%, 35.6%]</sub> | **64.0%** (16 / 25)<br><sub>95% CI: [44.5%, 80.0%]</sub> | **Std: 15.0%**<br>**Sem: 60.4%** | 2 / 8 |
| **Frozen Holdout Track** | 6 | 18 | **0.0%** (0 / 18)<br><sub>95% CI: [0.0%, 17.6%]</sub> | **61.1%** (11 / 18)<br><sub>95% CI: [38.6%, 80.0%]</sub> | **Std: 0.0%**<br>**Sem: 61.1%** | **4 / 6** |

*Note: Wilson score 95% confidence intervals reported due to sample sizes ($n=25, n=18$).*

### 4.3. Key Scientific Takeaways
1. **Generic Constraint Blind Spot:** Across the 18 valid holdout mutations, generic constraint checks (`not_null`, `unique`, `accepted_values`) caught 0 defects (0% catch rate). Column constraints cannot observe relational or arithmetic shifts that preserve table row shape.
2. **Semantic Invariant Generalization:** SRE semantic assertions caught 11 of 18 valid holdout mutations (61.1% pooled; +61.1 percentage points gain), generalizing to unseen schemas (ARR, chargebacks, take rates, compute burn, readmission).
3. **Surviving Defect Transparency:** Surviving defects are not hidden; they are cataloged under a controlled taxonomy (`MISSING_CONTRACT`, `WEAK_FIXTURE`, `ASSERTION_GAP`, `MUTATION_ORACLE_GAP`) with actionable remediation recipes.

---

## 5. Trust Boundaries & Operational Governance

Enterprise data governance requires clear boundaries between automated evaluation and human accountability:

```text
[Data / Analytics Engineers] ────────► Author & Approve Metric Contracts (Git)
                                              │
                                              ▼
[AI Text-to-SQL Agent] ──────────────► Submit Generated Query
                                              │
                                              ▼
[SRE Firewall Engine] ───────────────► Deterministic Evaluation (No Silent Rewrites)
                                              │
                                     ┌────────┴────────┐
                                     ▼                 ▼
                              [Compliant]        [Non-Compliant]
                                     │                 │
                                     ▼                 ▼
                          [Warehouse Exec]     [DENY or REQUIRE_REVIEW]
                                                       │
                                                       ▼
[Analytics Steward / Human-in-the-Loop] ◄──── Review Violation & Override
```

### Governance Principles:
1. **No Silent Query Rewrites:** SRE will never alter an agent's query behind the scenes. If a query violates a contract, it is explicitly blocked or tagged. Silent rewrites shift legal and financial liability to the platform vendor.
2. **Deterministic Pre-Execution Verification:** Contract evaluation is fully deterministic, based on SQL AST invariant comparison and commutative boolean normalization—not LLM-as-a-Judge heuristics.
3. **Signals, Not Causal Proof:** Layered statistical probes emit structured alerts indicating *empirical data shift*, explicitly mandating human review before re-baselining.

---

## 6. Enterprise Deployment Patterns

SRE supports multiple enterprise integration topologies:

### Pattern A: Kubernetes Sidecar Proxy (Zero-Code Agent Wrapper)
Deployed in the same Kubernetes pod as the Text-to-SQL agent or microservice. The agent submits queries to `http://127.0.0.1:8080/evaluate` before executing against the warehouse.

### Pattern B: CI/CD Pipeline Gate (dbt / Dataform)
Integrated into GitHub Actions or GitLab CI. Blocks Pull Requests if modified SQL data models introduce semantic drift against declared metric contracts (`sre check --metric <yaml> --candidate <sql> --fail-on-drift`).

### Pattern C: Asynchronous Replay Cron Worker
Consumes Fluentd/Datadog audit streams, replays production queries against historical DuckDB snapshots, and automatically files GitHub Pull Requests to patch contract definitions when blind spots are discovered.

---

## 7. Known Limitations & Threat Model

Transparency regarding platform scope and scientific boundaries is essential for enterprise security and audit reviews:

1. **Contract Completeness:** SRE evaluates queries against declared contracts. If a metric contract omits a business rule, the firewall cannot infer the unstated rule.
2. **Fixture Contrast Dependency:** Mutation testing requires fixture data with empirical contrasts (e.g. active and inactive records). Models with uniform data are marked `INCONCLUSIVE (LOW)` rather than claiming false test coverage.
3. **Operator–Assertion Coupling:** The benchmark evaluates mutation classes supported by the AST generator. True external generalization requires continuous expansion of mutation operators.
4. **Data Reality Decoupling:** Statistical probes detect statistical divergence, but cannot identify whether the shift represents a legitimate business trend or an upstream schema defect without human domain verification.

---

## 8. Strategic Roadmap

```text
[Phase 0.4.0 - 7]    Core Mutation Engine & Frozen Dual-Track Benchmark     (Completed)
[Phase 8.1]          Audit-Only Semantic Firewall (FastAPI / K8s Sidecar)    (Completed)
[Phase 8.2]          Self-Healing Replay Worker & Automated Contract Patcher (Completed)
[Phase 8.3]          Layered Statistical Reality Probes (Observability)      (Completed)
        │
        ▼
[Phase 8.4]          Contract-Grounded Evaluation Dataset Generator          (Next)
[Phase 9.0]          Native Enterprise Warehouse Adapters & OpenTelemetry
[Phase 10.0]         Multi-Tenant Enterprise Contract Registry & RBAC
[Phase 11.0]         Independent Third-Party External Benchmark Replication
[Phase 12.0]         Open Semantic Reliability Standards (OASIS / Linux Foundation)
```

---

## 9. Conclusion

The Semantic Reliability Control Plane provides the missing operational bridge between AI generation and enterprise data correctness. By replacing unstructured trust with declarative contracts, mutation-calibrated testing, runtime firewall enforcement, and layered observability, organizations can safely scale autonomous analytics agents while maintaining total auditability and governance.

---
*For questions, architectural reviews, or benchmark reproduction, visit [github.com/anandkrshnn-ai/semantic-reliability-engine](https://github.com/anandkrshnn-ai/semantic-reliability-engine).*
