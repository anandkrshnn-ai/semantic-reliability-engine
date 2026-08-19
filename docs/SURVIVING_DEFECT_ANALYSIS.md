# 🔍 Surviving Defect Root-Cause Analysis (Holdout Corpus)

This document provides a root-cause error analysis of valid mutations that survived semantic assertions during evaluation of the 6-model **Frozen Holdout Benchmark Track**.

---

## 📊 Summary of Surviving Mutations

| Mutation ID | Holdout Model | Operator | Root Cause Category | Specific Code | Severity | Recommended Remediation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ROAS_002` | `ad_campaign_roas` | `BOUNDARY_SHIFT` | `MISSING_CONTRACT` | `ATTRIBUTION_WINDOW_UNDECLARED` | `HIGH` | Add `temporal_bounds_assertion(max_attribution_days=30)` |
| `READMISSION_001` | `hospital_readmission_rate` | `FILTER_DROP` | `MISSING_CONTRACT` | `INDEX_ADMISSION_DENOMINATOR_UNCONSTRAINED` | `HIGH` | Add `required_population(required_filter='is_planned_readmission = false')` |
| `TAKE_RATE_002` | `marketplace_take_rate` | `AGGREGATION_SWAP` | `ASSERTION_GAP` | `NUMERATOR_DENOMINATOR_LINKAGE_MISSING` | `MEDIUM` | Add strict numerical point `metric_value` assertion with tight tolerance |
| `CHARGEBACK_001` | `fintech_chargeback_rate` | `COALESCE_BYPASS` | `MUTATION_ORACLE_GAP` | `EQUIVALENT_ON_FIXTURE_DENOMINATOR` | `LOW` | Expand fixture to include explicit `NULL` dispute flags |

---

## 🛠️ Root-Cause Breakdown

### 1. `ad_campaign_roas` — `ATTRIBUTION_WINDOW_UNDECLARED`
- **Injected Fault:** The campaign comparison boundary mutated from `is_test_campaign = false` to inclusive testing.
- **Why Standard Tests Passed:** Output tables retained non-null columns (`channel`, `roas`), and row counts matched expected groups.
- **Why Semantic Tests Missed:** The metric contract declared population filters but omitted a temporal attribution window invariant.
- **Remediation:** Declare `invariants.time.attribution_window_days: 30` in `contract.yaml`.

### 2. `hospital_readmission_rate` — `INDEX_ADMISSION_DENOMINATOR_UNCONSTRAINED`
- **Injected Fault:** Dropped exclusion filter `is_planned_readmission = false`.
- **Why Standard Tests Passed:** Output was a valid bounded float between 0.0 and 1.0.
- **Why Semantic Tests Missed:** Assertion suite only checked `min_value: 0.0` / `max_value: 1.0` without declaring index-discharge denominator constraints.
- **Remediation:** Add `RequiredPopulationAssertion` for `is_planned_readmission = false`.

### 3. `marketplace_take_rate` — `NUMERATOR_DENOMINATOR_LINKAGE_MISSING`
- **Injected Fault:** Swapped `SUM(commission_fee)` to `AVG(commission_fee)`.
- **Why Standard Tests Passed:** Floats remained non-null.
- **Why Semantic Tests Missed:** Ratio bounds remained between 5% and 30%.
- **Remediation:** Add strict `metric_value` expected point assertion with tolerance.

---

## 🏷️ Controlled Taxonomy Reference
- `MISSING_CONTRACT`: Contract lacks explicit semantic invariant declaration.
- `WEAK_FIXTURE`: Fixture lacks empirical contrast to provoke metric divergence.
- `UNSUPPORTED_DIALECT`: Dialect AST features unhandled by transpiler.
- `ASSERTION_GAP`: Assertion suite lacks tight threshold or relational checks.
- `MUTATION_ORACLE_GAP`: Mutation produces equivalent output on small fixture sample.
- `RESULT_COMPARISON_GAP`: Row shape/order matching was insufficient.
