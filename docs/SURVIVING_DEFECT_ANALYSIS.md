# 🔍 Surviving Defect Root-Cause Analysis (Holdout Corpus)

This document provides a root-cause error analysis of valid mutations that survived semantic assertions during evaluation of the 6-model **Frozen Holdout Benchmark Track**.

> **v1.1 Amendment status:** `READMISSION_001` and `TAKE_RATE_002` were remediated under holdout protocol **v1.1** (`v1.1.0-holdout-repair`). The v1.0 analysis and its recommended remediations are preserved below, annotated with corrections discovered during implementation. `ROAS_002` and `CHARGEBACK_001` remain open by design — surviving defects are the benchmark's diagnostic purpose.

---

## 📊 Summary of Surviving Mutations

| Mutation ID | Holdout Model | Operator | Root Cause Category | Specific Code | Severity | Remediation | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ROAS_002` | `ad_campaign_roas` | `BOUNDARY_SHIFT` | `MISSING_CONTRACT` | `ATTRIBUTION_WINDOW_UNDECLARED` | `HIGH` | Add `temporal_bounds_assertion(max_attribution_days=30)` | 🟡 OPEN |
| `READMISSION_001` | `hospital_readmission_rate` | `FILTER_DROP` | `MISSING_CONTRACT` | `INDEX_ADMISSION_DENOMINATOR_UNCONSTRAINED` | `HIGH` | Fixture-grounded `metric_value` point oracle (`Σ rate = 0.5`, 5% tolerance) + `expected_grain` + contract aggregation invariant (see §2 correction) | ✅ FIXED (v1.1) |
| `TAKE_RATE_002` | `marketplace_take_rate` | `AGGREGATION_SWAP` | `ASSERTION_GAP` + `WEAK_FIXTURE` | `NUMERATOR_DENOMINATOR_LINKAGE_MISSING` | `MEDIUM` | Diversified commission ratios (uniform 15% fixture made the metric ratio-invariant), `metric_value` point oracle (`Σ = 0.2667`, 5% tolerance) + `expected_grain` + contract aggregation invariant | ✅ FIXED (v1.1) |
| `CHARGEBACK_001` | `fintech_chargeback_rate` | `COALESCE_BYPASS` | `MUTATION_ORACLE_GAP` | `EQUIVALENT_ON_FIXTURE_DENOMINATOR` | `LOW` | Expand fixture to include explicit `NULL` dispute flags | 🟡 OPEN |

---

## 🛠️ Root-Cause Breakdown

### 1. `ad_campaign_roas` — `ATTRIBUTION_WINDOW_UNDECLARED`
- **Injected Fault:** The campaign comparison boundary mutated from `is_test_campaign = false` to inclusive testing.
- **Why Standard Tests Passed:** Output tables retained non-null columns (`channel`, `roas`), and row counts matched expected groups.
- **Why Semantic Tests Missed:** The metric contract declared population filters but omitted a temporal attribution window invariant.
- **Remediation:** Declare `invariants.time.attribution_window_days: 30` in `contract.yaml`.

### 2. `hospital_readmission_rate` — `INDEX_ADMISSION_DENOMINATOR_UNCONSTRAINED` ✅ FIXED (v1.1)
- **Injected Fault:** Dropped exclusion filter `is_planned_readmission = false`.
- **Why Standard Tests Passed:** Output was a valid bounded float between 0.0 and 1.0.
- **Why Semantic Tests Missed:** Assertion suite only checked `min_value: 0.0` / `max_value: 1.0` without declaring index-discharge denominator constraints.
- **⚠️ Original remediation correction:** The initially recommended `RequiredPopulationAssertion` is **unworkable on this fixture** — the assertion joins output entities to the source table via a single `join_key`, and no key exists whose cohort check passes the *unmutated* baseline (departments legitimately present in output contain rows violating each exclusion filter). The shipped repair instead adds a fixture-grounded point oracle (`expected: 0.5`, Σ of per-department rates on the deterministic fixture, 5% tolerance) plus `expected_grain` and a contract `aggregation` invariant. Semantic catch: 0% → 100%.

### 3. `marketplace_take_rate` — `NUMERATOR_DENOMINATOR_LINKAGE_MISSING` ✅ FIXED (v1.1)
- **Injected Fault:** Swapped `SUM(commission_fee)` to `AVG(commission_fee)`.
- **Why Standard Tests Passed:** Floats remained non-null.
- **Why Semantic Tests Missed:** Ratio bounds remained between 5% and 30%.
- **v1.1 post-mortem — three stacked defects, not one:** (a) *assertion gap* (bounds only, no point oracle, no grain assertion); (b) *weak fixture* — every row carried an identical 15% commission ratio, making the metric mathematically insensitive to population mix (two of three mutations survived purely because Σ stayed inside `[0.05, 0.3]`); (c) *scorer blindness* — the `INCONCLUSIVE (LOW)` grade was driven by fixture adequacy scoring 50%, because the v1.0 adequacy checker matches columns by a hardcoded name list and was blind to `gmv_amount`/`commission_fee` (typed numerics), `seller_id` (duplicate entity), and boolean flags. Repairs: diversified ratios (10–20%), point oracle `expected: 0.2667` ±5%, `expected_grain`, contract aggregation invariant, and the type-aware adequacy checks (fixture adequacy policy v1.1.0). Semantic catch: 33.3% → 100%; validity → `CONCLUSIVE (HIGH)`.

### 4. `fintech_chargeback_rate` — `EQUIVALENT_ON_FIXTURE_DENOMINATOR`
- **Injected Fault:** Removed `COALESCE` handling for unclassified disputes.
- **Why Standard Tests Passed:** Output was valid numerical ratio.
- **Why Semantic Tests Missed:** Survived as equivalent because no unclassified `NULL` disputes existed in the 5-row fixture.
- **Remediation:** Introduce `NULL` records into the fixture dataset.

---

## 🏷️ Controlled Taxonomy Reference
- `MISSING_CONTRACT`: Contract lacks explicit semantic invariant declaration.
- `WEAK_FIXTURE`: Fixture lacks empirical contrast to provoke metric divergence.
- `UNSUPPORTED_DIALECT`: Dialect AST features unhandled by transpiler.
- `ASSERTION_GAP`: Assertion suite lacks tight threshold or relational checks.
- `MUTATION_ORACLE_GAP`: Mutation produces equivalent output on small fixture sample.
- `RESULT_COMPARISON_GAP`: Row shape/order matching was insufficient.
