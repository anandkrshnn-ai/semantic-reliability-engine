# Release Notes: v1.0.0-phase7 (Research Preview)

**Tag:** `v1.0.0-phase7`  
**Target Commit:** `bf15bab42df55e609187253433158d8ea084b73c`  
**Status:** Pre-release / Research Preview  

---

## 📌 Positioning & Overview
> **Semantic mutation testing for analytics: measuring whether data-quality test suites and agentic SQL systems detect business-semantic defects.**

Traditional data-quality testing tools (dbt tests, Great Expectations, Monte Carlo) evaluate syntactic, volumetric, and schema constraints (null rates, uniqueness, schema type conformity). They do not, by themselves, test every business-semantic invariant—such as population exclusion filters, multi-component arithmetic deductions, or temporal attribution windows.

`semantic-reliability-engine` provides a formal framework for compiling declarative metric contracts, injecting AST-level relational mutations, auditing test adequacy on local DuckDB execution, and evaluating agent-generated analytical SQL.

---

## 🏆 Dual-Track Empirical Benchmark Findings

Across a 14-model benchmark evaluated under **Scientific Validity Policy v1.0**:

| Benchmark Track | Total Valid Defects ($V$) | Standard dbt Catch Rate | Semantic Suite Catch Rate | Incremental Gain ($\Delta$) | High-Confidence Models |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Development Track** (8 models) | 24 | 15.0% | 60.4% | **+45.4 percentage points** | 2 / 8 |
| **Frozen Holdout Track** (6 models) | 18 | **0.0%** | **61.1%** | **+61.1 percentage points** | **4 / 6** |

> **Key Empirical Finding:** Across the 18 valid executable mutations in the frozen holdout corpus, standard dbt-style checks detected 0 defects, producing a 0% mutation catch rate for this benchmark. Policy-driven semantic assertions detected **61.1%** of injected faults (+61.1 percentage points incremental gain), demonstrating generalization beyond development models.

---

## 🔬 Key Scientific & Technical Deliverables

### 1. Frozen Holdout Protocol & Verification
- **Immutable Protocol Metadata (`benchmark_corpus/holdout/holdout_protocol.yaml`):** Versioned baseline locked to prevent circular benchmark advantages.
- **Runtime Verifier (`ProtocolVerifier`):** Validates commit SHA and outputs runtime freeze verification status (`protocol_integrity: VERIFIED`).

### 2. Denominator-Precise Mathematical Accounting
Enforces strict mathematical accounting identities:
$$G = E + U + V \quad \text{and} \quad V = D + S$$
$$\text{Effective Catch Score} = \begin{cases} 100 \times \frac{D}{V}, & V > 0 \\ \text{NOT\_APPLICABLE}, & V = 0 \end{cases}$$
*(Where $G$ = generated, $E$ = equivalent on fixture, $U$ = unexecutable, $V$ = valid executable defects, $D$ = detected, $S$ = surviving).*

### 3. Surviving-Defect Root-Cause Taxonomy
- Machine-readable classification schema ([`docs/SURVIVING_DEFECT_ANALYSIS.md`](https://github.com/anandkrshnn-ai/semantic-reliability-engine/blob/main/docs/SURVIVING_DEFECT_ANALYSIS.md)) categorizing surviving holdout defects under `MISSING_CONTRACT`, `WEAK_FIXTURE`, `ASSERTION_GAP`, and `MUTATION_ORACLE_GAP` with concrete remediation recipes.
- CLI flag `--error-analysis` formats real-time root-cause diagnostic tables.

### 4. Agentic Analytics SQL Semantic Evaluator (`sre evaluate-agent`)
- Evaluates whether LLM/Agent-generated SQL satisfies declared metric contracts and passes mutation adequacy checks.
- Disentangles syntactic execution success from semantic correctness and flags unsupported model assumptions.

### 5. Multi-Dialect AST Compiler & Normalization
- Normalizes commutative boolean chains (`A AND B` $\equiv$ `B AND A`) and unwraps parentheses to eliminate false alarms on cosmetic refactors.
- Transpiles to Snowflake, BigQuery, Postgres, and DuckDB.

---

## ⚠️ Scope & Scientific Limitations
- **Corpus & Policy Scoped:** Results reflect local DuckDB execution across the 14 defined benchmark models under Validity Policy v1.0. No claim of universal production semantic coverage is made without domain-specific assertion configuration.
- **Fixture Contrast Dependency:** Semantic mutation detection requires empirical fixture contrasts (e.g. active vs inactive records); models with low fixture contrast are explicitly marked `INCONCLUSIVE (LOW)` rather than conflated with assertion failures.

---

## 🧪 Verification & Reproduction
```bash
# Clone and install
git clone https://github.com/anandkrshnn-ai/semantic-reliability-engine.git
cd semantic-reliability-engine
pip install -r requirements.txt

# Run complete test suite (70 tests)
pytest tests/ -v

# Run the frozen holdout benchmark with root-cause error analysis
python -m semantic_reliability.cli benchmark-corpus --split holdout --error-analysis
```
