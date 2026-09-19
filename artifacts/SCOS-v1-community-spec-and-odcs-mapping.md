# Semantic Contract Open Standard (SCOS) v1.0

**Community specification (individual draft)**  
**Status:** Draft for review — not an IETF, ISO, or consortium standard  
**Date:** 2026-09-19  
**Source snapshot:** `anandkrshnn-ai/semantic-reliability-engine` branch `main` @ `53cd696`  
**Companion schema:** `spec/scos-v1.schema.json` (must be reconciled with the live corpus before any external submission)  
**License of this text:** CC BY 4.0; reference implementation Apache-2.0

This document is the short, venue-agnostic write-up. It is shaped like an individual Internet-Draft (problem, non-goals, normative core, conformance, IANA-style registry notes) but is **not** submitted to RATS or any IETF working group.

---

## Abstract

SCOS defines a vendor-neutral document format for *query-level* business-metric contracts. A contract binds a named metric to (1) a canonical SQL implementation, (2) deterministic AST invariants (grain, population, deduction, join), and (3) optional statistical reality probes. A conforming implementation validates candidate SQL against those invariants and MAY execute contrastive fixtures. SCOS does not replace table-level data contracts, IAM, or natural-language agent-tool policies.

Empirical numbers in this draft are taken only from `benchmark_ladder_scorecard.json` on `main` @ `53cd696` (timestamp `2026-09-19T14:24:47Z`) and from the author-verified unit-test count on that branch. Live LLM evaluation is out of scope.

---

## 1. Problem

Warehouse engines accept syntactically valid SQL that is the wrong business metric. Typical failures:

- required population filters dropped (`status = 'active'`, `is_test_account = false`);
- grain shifted by a join that multiplies rows;
- deduction omitted (`amount - refund`);
- numerator and denominator of a rate decoupled.

Table-level quality checks (`not_null`, `unique`, row-count bounds) and single-domain dbt suites do not detect these failures when the result table still has the expected shape.

Natural-language agent governance (for example Gemini Enterprise Semantic Governance) evaluates proposed *tool calls* against user intent and English constraints. It does not evaluate whether generated SQL preserves a declared metric. Those layers compose; they are not substitutes.

---

## 2. Non-goals

SCOS MUST NOT be described as:

- an identity or attestation protocol (that is PTV / RATS);
- a replacement for ODCS, Open Data Product Standard, or dbt YAML;
- a replacement for IAM, Model Armor, or Gemini Enterprise Semantic Governance;
- a live-agent leaderboard.

This draft does not claim IETF working-group adoption. Success looks like the PTV -00 shape: a dated individual specification plus a public reference implementation and test vectors.

---

## 3. Terminology

The key words MUST, MUST NOT, SHOULD, and MAY are to be interpreted as in RFC 2119 / RFC 8174.

- **Metric contract:** a SCOS document identifying one business metric.
- **Candidate SQL:** SQL an agent or human proposes as an implementation of that metric.
- **Invariant:** a deterministic AST-level constraint the candidate MUST satisfy.
- **Reality probe:** a statistical bound over warehouse or fixture data; observational, not a substitute for invariants.
- **Verdict:** `ALLOW`, `REQUIRE_REVIEW`, or `DENY`. Implementations MAY also return `ABSTAIN`.

---

## 4. Document model

A SCOS v1 document MUST be YAML or JSON and MUST declare `scos_version: "1.0.0"` once that field is frozen in both the schema and the corpus. Until schema/corpus reconciliation lands, implementers MUST treat `scos_version` / `contract_version` drift as a blocker, not as dual-valid syntax.

A contract has four layers.

### 4.1 Identity

| Field | Requirement |
|---|---|
| `id` | Canonical URN `urn:scos:<domain>:<metric_slug>` |
| `metric` | Stable slug |
| `version` | SemVer of the *metric meaning*, not the SCOS spec |
| `domain` | Owning domain (e.g. `finance`) |
| `grain` | Reporting grain (`<entity>_<period>` or explicit column list) |
| `dialect` | One of `bigquery`, `snowflake`, `databricks`, `duckdb`, `postgres`, `redshift` |
| `owner` | Accountable mailbox or team |

### 4.2 Canonical SQL

`sql` is the human-authorized ground truth. It is the oracle for mutation tests, dry-runs, and replay. Implementations MUST NOT silently rewrite candidate SQL to match it.

### 4.3 Invariants (normative static layer)

Implementations MUST be able to check at least:

- **Population:** `required_filters` present (logical entailment on the WHERE/HAVING tree, not string equality); `forbidden_filters` absent.
- **Grain:** required GROUP BY / partition dimensions present; extra dimensions MAY be flagged `REQUIRE_REVIEW`.
- **Deduction / aggregation:** required subtracted terms present; required numerator/denominator coupling preserved when declared.
- **Join:** only declared relationship paths; fan-out joins that change grain MUST `DENY` or `REQUIRE_REVIEW`.

Cosmetic formatting and commutative reordering MUST NOT by themselves produce `DENY`.

### 4.4 Reality probes (optional runtime layer)

Probes MAY declare population rates, implication confidence, and null-drift ceilings. Probe failure SHOULD be `REQUIRE_REVIEW` unless the contract marks the probe as blocking.

---

## 5. Enforcement interface

A conforming runtime SHOULD expose a read-only interface. The reference MCP tool set is:

| Tool | Effect |
|---|---|
| `scos_list_metrics` | Discover contracts the caller is authorized to see |
| `scos_get_contract` | Return canonical SQL and invariants |
| `scos_validate_sql` | Return verdict + violation list |
| `scos_explain_violation` | Remediation text; MUST NOT mutate SQL |
| `scos_get_probe_status` | Probe health |

Security constraints for any network exposure:

- MUST NOT execute candidate SQL on a production warehouse from the validator process.
- MUST NOT expose write/update/patch tools for contracts at runtime.
- MUST reject multi-statement SQL and DDL/DML with `DENY`.
- SHOULD record each decision as a hash-chained audit event over `sql_sha256`, `metric_id`, verdict, and caller identity — not over raw SQL literals.

This is a control-plane consultant, not a query proxy.

---

## 6. Conformance

A system is SCOS v1.0 compliant if it:

1. Validates documents against the published JSON Schema once schema and corpus agree.
2. Performs deterministic AST invariant checks that are stable under formatting and commutativity.
3. Emits a machine-readable verdict plus a SHA-256 evidence digest of `(contract_id, contract_version, sql_sha256, verdict, invariant_ids)`.
4. Publishes pass/fail against the frozen Semantic-SQL-Bench holdout vectors, or an equivalent independently specified vector pack.

A system that only wraps an LLM over English metric docs is not compliant.

---

## 7. Evaluation claim (frozen to this snapshot)

Mutation benchmark on `main` @ `53cd696`, file `benchmark_ladder_scorecard.json`:

- 14 metric models (8 development, 6 frozen holdout)
- 45 valid injected defects
- No language model in the loop

| Tier | Mechanism | Caught | Rate |
|---|---|---:|---:|
| 0 | Syntax only (sqlglot parse) | 0/45 | 0.0% |
| 1 | Minimal structural (`not_null` / unique / row-count bounds) | 4/45 | 8.9% |
| 2 | Realistic dbt suite (jaffle_shop-derived) | 4/45 | 8.9% |
| 3 | Static SCOS AST linter | 28/45 | 62.2% |
| 4 | Runtime relational oracle (DuckDB fixtures) | 37/45 | 82.2% |

Honest increments on this snapshot:

- Tier 4 vs Tier 1/2: **+73.3 pp**
- Tier 4 vs Tier 3: **+20.0 pp** (scorecard 82.22 − 62.22; cite as +19.9 pp if rounding both to one decimal as in the README table)

These numbers measure *mutation catch on authored defects and fixtures*. They are not live-agent accuracy.

Unit tests: **144** on current `main`, author-verified after the crash-masking fix. Do not cite the earlier 112-test / +61.1 pp snapshot.

Open defects and fixture repairs for the holdout track are documented in `docs/SURVIVING_DEFECT_ANALYSIS.md` (protocol v1.1). Surviving mutants are diagnostic, not a reason to inflate catch rate.

---

## 8. Relationship to other layers

```
PTV / RATS          who is the agent, hardware-bound
Gemini NLC policy   may this tool call proceed given user intent
SCOS                does this SQL preserve the authorized metric
ODCS                what is the table/product contract between producer and consumer
```

Optional future composition (not in this draft): bind the SCOS evidence digest from §6.3 into a SCITT or EAT payload so an attested agent can prove *which contract version* authorized a query. That note belongs next to PTV, not instead of this specification.

---

## 9. Venue

Do not submit this document to IETF RATS as a protocol.

Intended first readers:

1. Bitol / ODCS community — as a query-invariant profile, not a competing contract kind.
2. dbt / MetricFlow implementers — `compiled_sql` gate.
3. Academic eval workshops — Semantic-SQL-Bench vectors.
4. NIST NCCoE agent-authorization follow-on — SCOS as decision evidence, PTV as identity evidence.

---

## Appendix A. ODCS mapping (informative)

ODCS v3.x (Bitol, Apache-2.0) is a *producer/consumer data contract*: fundamentals, schema/properties, quality, SLA, servers, roles, authoritative definitions. SCOS is a *metric/query contract*. Mapping rule: **SCOS rides in ODCS custom properties and authoritative definitions; it does not fork ODCS `kind`.**

### A.1 Field map

| SCOS | ODCS v3.x home | Notes |
|---|---|---|
| `id` (`urn:scos:…`) | `authoritativeDefinitions[]` type `canonical` plus `customProperties.scosId` | Keep ODCS `id` as the dataset/product UUID |
| `metric` / `version` | `customProperties.scosMetric`, `customProperties.scosMetricVersion` | Distinct from ODCS document `version` |
| `domain` | ODCS `domain` | Align strings |
| `owner` | ODCS `team[]` | |
| `grain` | schema `dataGranularityDescription` + `customProperties.scosGrain` | ODCS grain text is descriptive; SCOS grain is enforceable |
| `dialect` / `sql` | `servers[].type` + `customProperties.scosCanonicalSql` | Canonical SQL is not an ODCS schema property |
| invariants | `quality[]` is insufficient | ODCS quality is table/column tests. Put AST invariants under `customProperties.scosInvariants` |
| probes | `quality[]` of type custom / library | Population rates MAY be expressed as ODCS quality rules; implication probes usually cannot |
| verdict evidence | out of ODCS scope | Emit separately; link from `authoritativeDefinitions` type `implementation` |

### A.2 Recommended ODCS fragment

```yaml
kind: DataContract
apiVersion: v3.2.0
id: "53581432-6c55-4ba2-a65f-72344a91553a"
version: "1.1.0"
status: active
domain: finance
name: transactions_net_revenue_product

authoritativeDefinitions:
  - type: canonical
    url: "urn:scos:finance:net_revenue"
    description: SCOS metric identity for net_revenue
  - type: implementation
    url: "https://github.com/anandkrshnn-ai/semantic-reliability-engine/blob/main/spec/SCOS_V1_SPECIFICATION.md"

schema:
  - name: transactions
    physicalType: table
    dataGranularityDescription: customer_id x calendar month

customProperties:
  - property: scosProfile
    value: "scos-v1.0-query-invariants"
  - property: scosId
    value: "urn:scos:finance:net_revenue"
  - property: scosMetricVersion
    value: "1.2.0"
  - property: scosGrain
    value: "customer_month"
  - property: scosCanonicalSqlRef
    value: "contracts/finance/net_revenue.yaml#sql"
  - property: scosInvariantsRef
    value: "contracts/finance/net_revenue.yaml#invariants"
```

A processor that understands only ODCS MUST still treat the table contract as valid if `customProperties` are ignored. A processor that understands SCOS MUST load `scosInvariantsRef` and apply §4.3.

### A.3 What not to do

- Do not encode required WHERE predicates as ODCS `quality` `unique` / `null` checks.
- Do not replace ODCS `schema.properties` with SCOS documents.
- Do not claim ODCS compliance for a standalone SCOS YAML file.

---

## Appendix B. Open blockers before external send

These are known on `main` and are part of this draft’s honesty requirements:

~~1. Freeze a single `scos_version` string in spec, JSON Schema, and every corpus contract.~~ *(Resolved in `3323f0c`)*
~~2. Reconcile `spec/scos-v1.schema.json` with the live corpus (currently still divergent).~~ *(Resolved in `3323f0c`)*
~~3. Host the schema at a stable URL; do not cite `semantic-reliability.dev` until that host serves the file.~~ *(Resolved via GitHub tagged release `v1.0.0`)*
4. Point default clone / docs at `main` (`53cd696` and later). `master` is a stale snapshot (65 commits; 112-test README).
5. Keep live-agent adapters labeled experimental until a named-model run with frozen seeds is published.

*Note: With items 1, 2, and 3 resolved, the schema is stable, hosted, and fully reconciled with the corpus. The core blockers for external submission are cleared. Items 4 and 5 remain as general project health goals.*

---

## Appendix C. Change control

Cite this draft as:

> Damodaran, A. *Semantic Contract Open Standard (SCOS) v1.0 — Community Specification and ODCS Mapping.* Snapshot `53cd696`, 2026-09-19.

Revise the evaluation table only by pointing at a new scorecard commit. Do not edit historical percentages in place.
