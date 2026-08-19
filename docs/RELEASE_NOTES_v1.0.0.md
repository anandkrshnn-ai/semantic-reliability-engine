# Release Notes: v1.0.0 (Research Preview)

**Tag:** `v1.0.0` (or `v1.0.0-phase7`)  
**Commit:** `bf15bab42df55e609187253433158d8ea084b73c`  
**Status:** Pre-release / Research Preview  

---

## 📌 Positioning & Scope
> **Semantic mutation testing for analytics: measuring whether data-quality test suites and agentic SQL systems detect business-semantic defects.**

Traditional data-quality testing frameworks (such as generic dbt schema tests, Great Expectations column constraints, and volumetric anomaly monitors) validate syntactic structure, uniqueness, and null boundaries. They do not, by themselves, test every business-semantic invariant—such as population exclusion filters, arithmetic deductions (e.g. subtracting refunds or spot instance credits), or temporal attribution windows.

`semantic-reliability-engine` provides a formal framework for compiling declarative metric contracts, injecting AST-level relational mutations, auditing test suite adequacy on local DuckDB execution, and evaluating agent-generated analytical SQL against declared business semantics.

---

## 🏆 Empirical Benchmark Findings (Dual-Track Protocol)

Evaluated under [Scientific Validity Policy v1.0](https://github.com/anandkrshnn-ai/semantic-reliability-engine/blob/main/docs/BENCHMARK_METHODOLOGY.md#4-decision-policy--scientific-validity-matrix) across 14 canonical models:

| Benchmark Track | Models | Valid Defects (V) | Generic Constraint Catch (Pooled) | Semantic Suite Catch (Pooled) | Macro-Average Catch Rate | Certified Conclusive Models |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Development Track** | 8 | 25 | **16.0%** (4 / 25)<br><sub>95% CI: [5.3%, 35.6%]</sub> | **64.0%** (16 / 25)<br><sub>95% CI: [44.5%, 80.0%]</sub> | **Std: 15.0%**<br>**Sem: 60.4%** | 2 / 8 |
| **Frozen Holdout Track** | 6 | 18 | **0.0%** (0 / 18)<br><sub>95% CI: [0.0%, 17.6%]</sub> | **61.1%** (11 / 18)<br><sub>95% CI: [38.6%, 80.0%]</sub> | **Std: 0.0%**<br>**Sem: 61.1%** | **4 / 6** |

*Note on confidence intervals: Wilson score 95% intervals reported due to sample sizes (n=25, n=18). Macro-average reflects unweighted mean of individual model scores.*  
*Certified Conclusive Models: Models meeting Validity Policy v1.0 thresholds (Fixture Adequacy >= 80% and Contract Coverage >= 60%).*

### 🔬 Key Empirical Findings:
1. **Generic Constraint Baseline:** Across the 18 valid executable mutations in the frozen holdout corpus, standard column-level constraint tests (`not_null`, `unique`, `accepted_values`) detected 0 defects, producing a 0% mutation catch rate for this benchmark. This is expected by construction: column-level generic constraints cannot observe table-level relational, filtering, or arithmetic shifts that preserve shape and non-null properties.
2. **Semantic Assertion Catch Rate:** Policy-driven semantic contract assertions caught 11 of 18 valid holdout mutations (61.1% pooled; 95% CI: [38.6%, 80.0%]), achieving a +61.1 percentage point incremental gain over generic constraint suites.
3. **Generalization Beyond Development Models:** 4 of the 6 holdout models achieved `CONCLUSIVE (HIGH)` validity status under Tier-2 realistic fixtures.

---

## 🔬 Core Scientific & Technical Deliverables

### 1. Frozen Holdout Protocol & Verification
- **Immutable Protocol Metadata (`benchmark_corpus/holdout/holdout_protocol.yaml`):** Versioned baseline locked to prevent circular benchmark advantages.
- **Runtime Verifier (`ProtocolVerifier`):** Verifies commit SHA at runtime and outputs freeze verification status (`protocol_integrity: VERIFIED`).

### 2. Denominator-Precise Mathematical Accounting
Enforces strict mathematical accounting identities to eliminate score inflation:
- Total Generated Mutations: `G = E + U + V`
- Valid Defect Decomposition: `V = D + S`
- Effective Catch Score:
  $$\text{Score} = \begin{cases} 100 \times \frac{D}{V}, & V > 0 \\ \text{NOT\_APPLICABLE}, & V = 0 \end{cases}$$
  *(Where `G` = generated, `E` = equivalent on fixture, `U` = unexecutable, `V` = valid executable defects, `D` = detected, `S` = surviving).*

### 3. Surviving-Defect Root-Cause Taxonomy
- Structured error analysis ([`docs/SURVIVING_DEFECT_ANALYSIS.md`](https://github.com/anandkrshnn-ai/semantic-reliability-engine/blob/main/docs/SURVIVING_DEFECT_ANALYSIS.md)) classifying surviving holdout defects under `MISSING_CONTRACT`, `WEAK_FIXTURE`, `ASSERTION_GAP`, and `MUTATION_ORACLE_GAP` with actionable remediation recipes.
- CLI flag `--error-analysis` formats real-time root-cause diagnostic tables.

### 4. Agentic Analytics SQL Semantic Evaluator (`sre evaluate-agent`)
- Evaluates whether LLM/Agent-generated SQL satisfies declared metric contracts and passes mutation adequacy checks.
- Disentangles syntactic execution success from semantic correctness and flags unsupported model assumptions.

### 5. Multi-Dialect AST Compiler & Normalization
- Normalizes commutative boolean chains (`A AND B` == `B AND A`) and unwraps parentheses to eliminate false alarms on cosmetic refactors.
- Transpiles declarative YAML metric definitions to Snowflake, BigQuery, Postgres, and DuckDB.

---

## ⚠️ Known Scientific Limitations & Threat Model

1. **Operator–Assertion Coupling (Co-Design):** The frozen holdout controls against model overfitting, but does not eliminate operator–assertion DSL coupling (mutations targeting classes of logic expressible in the contract schema). True external generalization requires independent third-party mutant authoring.
2. **Generic vs Singular Test Baseline:** The baseline benchmark evaluates standard generic dbt tests (`not_null`, `unique`, `accepted_values`). It does not include expert custom singular tests (e.g. hand-written SQL business assertions), which are recommended for future multi-arm benchmark expansions.
3. **Fixture Contrast Sensitivity:** Semantic mutation testing requires empirical fixture contrasts (e.g. active vs inactive records); models with low fixture contrast are explicitly classified as `INCONCLUSIVE (LOW)` rather than counted as assertion failures.

---

## 🧪 Reproduction Guide
```bash
# Clone repository
git clone https://github.com/anandkrshnn-ai/semantic-reliability-engine.git
cd semantic-reliability-engine

# Install dependencies
pip install -r requirements.txt

# Run complete unit test suite (70 tests)
pytest tests/ -v

# Run the frozen holdout benchmark with root-cause error analysis
python -m semantic_reliability.cli benchmark-corpus --split holdout --error-analysis
```
