# Semantic Reliability Engine (SRE / SCOS)

**Deterministic Semantic Contract Verification for LLM-Generated SQL via AST Mutation Analysis and Runtime Relational Invariants.**

## The Problem: Syntactic Validity ≠ Semantic Contract Preservation

Standard SQL generation evaluation relies on execution match against a single test database or basic AST parity. This misses critical semantic drift in production analytics:

* **Grain Shift**: A query runs without error, but joins duplicate dimensional rows, distorting aggregations.
* **Population Filter Bleed**: Scoping criteria (`WHERE status = 'ACTIVE' AND deleted_at IS NULL`) are omitted or misapplied across subqueries.
* **Numerator/Denominator Decoupling**: Aggregation logic drops dependent conditions, computing mathematically invalid ratios.

A query can return `200 OK` and non-empty rows while failing the underlying business logic contract.

## What SRE Does

SRE evaluates LLM-generated SQL against explicit Semantic Contract Specifications (SCOS) by subjecting queries to deterministic AST mutation analysis and fixture assertions:

* **AST Parsing & Invariant Extraction**: Parses candidate SQL into an intermediate AST representation, isolating target grains, join topologies, and projection expressions.
* **Mutation Testing**: Systematically introduces controlled semantic mutations (e.g., grain shifts, filter drops, aggregate mismatches) to generate mutant variants.
* **Contract Verification**: Executes candidate queries and mutants against calibrated fixture environments to test whether the candidate SQL truly enforces business invariants or passes accidentally.
* **Provenance & Audit Trails**: Validates lineage, citations, and contract adherence with strict validation gates.

## Installation

```bash
git clone https://github.com/anandkrshnn-ai/semantic-reliability-engine.git
cd semantic-reliability-engine
pip install -e .
```

## Quickstart (CLI)

### 1. Evaluate Candidate SQL Against a Contract
Evaluate a single generated query against a contract definition and fixture dataset:

```bash
sre evaluate-agent \
  --sql candidate.sql \
  --contract metric.yaml \
  --fixture data.csv
```

### 2. Audit Provenance
Mechanically verify external provenance claims, citations, and internal docs assertions:

```bash
sre audit-provenance \
  --target-dir benchmark_corpus \
  --strict
```

### 3. Run Benchmark Corpus Sweep
Execute the mutation test suite across the verified holdout split with full error categorization:

```bash
sre benchmark-corpus \
  --split holdout \
  --error-analysis \
  --json-out results.json
```

## Semantic Contract Example

Contracts declare structural and behavioral constraints that queries must preserve:

```yaml
contract_version: "1.0"
dataset: "enterprise_analytics"
target_grain:
  - "account_id"
  - "fiscal_period"
invariants:
  population_filters:
    must_include:
      - "is_active = TRUE"
      - "is_test_account = FALSE"
  aggregations:
    - metric: "churn_rate"
      numerator: "SUM(CASE WHEN churned THEN 1 ELSE 0 END)"
      denominator: "COUNT(DISTINCT account_id)"
      strictly_coupled: true
```

## Empirical Benchmark Results (Phase 3 Verified)

44 valid injected defects, independently reproduced across 14 analytical metric definitions in the benchmark corpus (8 development-track, 6 frozen-holdout-track). These are mutation-tested SQL metric definitions, not live LLM evaluations — no language model is in the loop for this benchmark.

| Evaluation Tier | Mechanism | Catch Rate | Key Finding |
|---|---|---|---|
| Tier 1 | Minimal structural checks (not_null, unique, row-count bounds) | 9.1% (4/44) | — |
| Tier 2 | Realistic dbt suite (sourced from dbt-labs/jaffle_shop) | 9.1% (4/44) | Adds zero incremental detection outside its source e-commerce domain — a single-domain data-quality suite doesn't generalize to heterogeneous analytical models |
| Tier 3 | Static SCOS AST Linter | 63.6% (28/44) | Catches structural grain shifts and dropped filters, zero query execution, sub-millisecond |
| Tier 4 | Runtime Relational Oracle | 81.8% (36/44) | Full semantic verification via contrastive fixture execution |

Full per-model breakdown and root-cause taxonomy: [docs/SURVIVING_DEFECT_ANALYSIS.md](docs/SURVIVING_DEFECT_ANALYSIS.md).

## Roadmap

- [ ] Publish complete holdout benchmark breakdown and per-model error topology.
- [ ] Expand AST mutation operators for complex window functions and recursive CTEs.
- [ ] Add native GitHub Action for automated SQL pull request semantic auditing.
- [ ] Wire live LLM providers (OpenAI / Anthropic / Ollama) into benchmark-live for a genuine model-vs-model evaluation track.
- [ ] Expand Tier 2's realistic dbt baseline beyond jaffle_shop to additional verified domains.

## License

Apache 2.0
