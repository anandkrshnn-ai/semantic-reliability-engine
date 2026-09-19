---
kind: business_term
name: Business Glossary
category: business_term
scope:
    - '**'
---

### SCOS
- Definition：Semantic Contract Open Standard — the project's vendor-neutral YAML/JSON specification for declaring business metrics as executable contracts containing identity headers, canonical ground-truth SQL, static AST invariants (required/forbidden filters, deductions, temporal grain), and runtime statistical probes. v1.0.0 is the official draft version with a published JSON schema.
- Aliases：SCOS v1.0、scos-v1.schema.json

### false green builds
- Definition：The failure mode the project targets: SQL that passes all standard structural tests (not_null, unique, row_count_bounds) and executes cleanly on a warehouse, but silently violates the business meaning of a metric (e.g., dropping required cohort filters or refund deductions).

### drift score
- Definition：The semantic drift metric between an agent-generated SQL query and its SCOS metric contract, defined conceptually as the Jaccard distance over normalized AST node sets. The README documents the formula; the current implementation uses a simplified penalty function instead of the full Jaccard computation.
- Aliases：D_sem、semantic drift

### holdout corpus
- Definition：The unseen subset of SCOS metric contracts (6 models under `benchmark_corpus/holdout/`) reserved for unbiased evaluation of catch rates after the model has been tuned on the dev corpus. Results are reported in `holdout_results.json`.

### dev corpus
- Definition：The training set of 8 SCOS metric contracts under `benchmark_corpus/dev/` used to develop and tune mutation operators and the guardrail policy before evaluating on the holdout set.

### mutation operator
- Definition：A chaos-mutation rule applied to semantically correct SQL to inject a specific semantic bug (e.g., removing a required filter, flipping an aggregation direction) for measuring whether the guardrail catches the drift. The project defines 8 such operators.

### baseline ladder
- Definition：A tiered evaluation framework comparing four strategies: Tier 1 Minimal (no tests), Tier 2 Realistic dbt (standard structural tests), Tier 3 Static SCOS (AST invariant linting), Tier 4 Runtime Oracle (warehouse execution). Catch rate, latency, and cost are compared across tiers to show that static AST linting matches runtime oracle performance at near-zero compute.
- Aliases：tiered baseline

### hybrid router
- Definition：A policy that combines Tier 3 static SCOS checks with Tier 4 runtime oracle checks, routing each query through the cheapest sufficient layer to achieve higher catch rate with lower latency than pure runtime evaluation.

### trajectory replay
- Definition：Zero-compute offline re-scoring of previously captured agent SQL trajectories (`runs/trajectories.jsonl`) against updated contracts, enabling regression testing without re-running live agents or paying for LLM calls.
- Aliases：offline replay

### gym module
- Definition：An experimental dataset formatting and generation module (`semantic_reliability/gym/`) classified as research scaffolding in the README's AI-assisted development disclosure; not part of the verified core and not suitable for production use without further validation.
- Aliases：gym/
