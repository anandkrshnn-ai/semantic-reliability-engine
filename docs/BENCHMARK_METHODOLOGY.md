# 🔬 Semantic Reliability Engine — Benchmark Methodology Specification

**Version:** `1.0.0`  
**Standard:** OASIS / Analytics Engineering Semantic Reliability  
**Corpus Architecture:** Dual-Track (8 Development Models, 6 Frozen Holdout Models)

---

## 1. Executive Summary

Traditional data quality testing tools (dbt tests, Great Expectations, Monte Carlo) evaluate **syntactic, volumetric, and schema characteristics**:
- Null rates
- Uniqueness constraints
- Schema type conformity
- Row volume anomalies

**The Blind Spot:** These tools fail to detect **relational logic shifts** where the SQL remains valid and data outputs conform to schema, but the analytical meaning is mutated (e.g. population filter dropped, arithmetic deduction omitted, join predicate lost).

This benchmark quantifies:
1. The rate at which standard data test suites produce **False Green Builds** on mutated queries.
2. The **Effective Semantic Catch Score** of policy-driven semantic contract assertions.
3. The **Generalization** across fresh, frozen holdout analytical models with Tier-2 realistic fixtures.

---

## 2. Injected Mutation Operator Taxonomy

The engine applies AST-level relational mutations across 8 deterministic vectors:

| Operator ID | AST Mutation Target | Business / Relational Impact |
| :--- | :--- | :--- |
| `FILTER_DROP` | Drop right conjunct of `WHERE` clause (`AND` condition) | Expands population (e.g. including cancelled/inactive records). |
| `BOUNDARY_SHIFT` | Invert comparison operators (`>` $\rightarrow$ `>=`, `=` $\rightarrow$ `!=`) | Mutates threshold criteria. |
| `AGGREGATION_SWAP` | Swap aggregate functions (`SUM` $\rightarrow$ `AVG`, `COUNT(DISTINCT)` $\rightarrow$ `COUNT`) | Alters mathematical payload while preserving row count. |
| `JOIN_PREDICATE_DROP` | Strip `ON` condition on non-cross joins | Triggers Cartesian product row explosion. |
| `GRAIN_DROP` | Drop dimension from `GROUP BY` clause | Alters reporting grain / entity uniqueness. |
| `MATH_OPERATOR_INVERT` | Invert arithmetic operator (`-` $\leftrightarrow$ `+`) | Omits deductions (e.g. adding refunds instead of subtracting). |
| `COALESCE_BYPASS` | Unwrap `COALESCE(col, default)` | Propagates null values downstream. |
| `DISTINCT_DROP` | Strip `DISTINCT` keyword from aggregate/select | Introduces duplicate multi-counting. |

---

## 3. Mathematical Metric Definitions

### A. Effective Catch Score
Mutations that cause zero output variance on fixture datasets are classified as `EQUIVALENT_ON_FIXTURE` and excluded from the denominator:

$$\text{Effective Catch Score} = \frac{\text{Valid Defects Detected by Assertions}}{\text{Total Injected Mutations} - \text{Equivalent on Fixture Mutations}} \times 100\%$$

### B. Incremental Gain ($\Delta$)
The net percentage point improvement provided by the semantic assertion suite over the standard baseline:

$$\text{Incremental Gain} = \text{Semantic Catch Score (\%)} - \text{Standard Catch Score (\%)}$$

### C. Contract Coverage Score
Measures whether a metric has declared all required semantic invariants for its domain class:

$$\text{Contract Coverage} = \frac{|\text{Declared Invariant Dimensions} \cap \text{Required Dimensions}|}{|\text{Required Dimensions}|} \times 100\%$$

---

## 4. Decision Policy & Scientific Validity Matrix

Thresholds defined in [`semantic_reliability/harness/validity_policy.yaml`](file:///c:/Users/Monika/Documents/GitHub/semantic-reliability-engine/semantic_reliability/harness/validity_policy.yaml):

| Validity Grade | Minimum Fixture Adequacy | Minimum Contract Coverage | Scientific Interpretation |
| :--- | :--- | :--- | :--- |
| **`CONCLUSIVE` (HIGH)** | $\ge 80\%$ | $\ge 60\%$ | Benchmark result is certified. Fixture contrasts and contracts support definitive conclusions. |
| **`QUALIFIED` (MEDIUM)** | $\ge 60\%$ | $\ge 40\%$ | Result is directional. Partial contract coverage or moderate fixture contrast. |
| **`INCONCLUSIVE` (LOW)** | $< 60\%$ | Any | Fixture lacks necessary empirical contrast. Low scores reflect fixture gaps, not tool failure. |

---

## 5. Dual-Track Evaluation Protocol

To prevent circular benchmark design (where assertions are tailored to known mutations):

1. **Development Track (`benchmark_corpus/dev/`):** 8 canonical models used to design initial operators and assertions.
2. **Frozen Holdout Track (`benchmark_corpus/holdout/`):** 6 independent models with Tier-2 realistic fixtures (duplicates, multi-cohort time boundaries, nulls, skewed values) frozen prior to evaluation.
