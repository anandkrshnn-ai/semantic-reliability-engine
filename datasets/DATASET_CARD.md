# SRE Semantic Gym Dataset Card

## Intended Use
This dataset is intended for the evaluation, alignment, and fine-tuning of Text-to-SQL agents and analytical LLMs. It provides contract-grounded preference pairs where the "chosen" response satisfies strict business semantic invariants and the "rejected" response introduces measurable semantic defects.

## Out-of-Scope Use
This dataset should not be used as a general-purpose SQL syntax corpus. It is strictly bound to the business ontologies defined in the source metric contracts. It is not a substitute for human financial auditing.

## Data-Generation Process
Generated via the SRE Phase 8.4.1 Evidence Pipeline. Baseline SQL is validated against DuckDB fixtures and declarative YAML contracts. AST mutations are injected, executed, and evaluated. Pairs are only retained if the mutation causes empirical result divergence AND violates a contract invariant or semantic assertion.

## Split Strategy
Splits are deterministic and leakage-resistant. Metric families are hashed and strictly assigned to `train`, `validation`, or `holdout`. Mutation types are further restricted per split to prevent cross-contamination of semantic concepts:
- **`train`**: `FILTER_DROP`, `AGGREGATION_SWAP`, `COALESCE_BYPASS`
- **`validation`**: `BOUNDARY_SHIFT`, `DISTINCT_DROP`
- **`holdout`**: `GRAIN_DROP`, `MATH_OPERATOR_INVERT`, `JOIN_PREDICATE_DROP` + domain holdouts (`healthcare`, `infrastructure`, `risk`)

## Known Biases & Limitations
- **Fixture Contrast Dependency:** The dataset only contains mutations that diverge on the provided synthetic fixtures. Real-world data distributions may yield different equivalence outcomes.
- **Contract Completeness:** The "rejected" SQL is only as defective as the contract is comprehensive. If a contract lacks an invariant, the mutation may survive and be excluded from the dataset.
- **No Causal Guarantees:** Statistical probes used in generation indicate correlation decay, not necessarily causal business definition shifts.

## Privacy Assumptions
All fixtures are synthetic or heavily anonymized. No PII is present in the SQL prompts or fixture data.

## License
Apache 2.0 (Codebase) / CC-BY-4.0 (Dataset Artifacts)
