# Strategic Roadmap: The Two-Engine Tradeoff Paper & Semantic-SQL-Bench

## 🎯 Executive Strategy & Sequence

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 1: The Two-Engine Systems Tradeoff Paper (Immediate Priority)         │
│  - Empirical study of Static AST Linter vs. Runtime Relational Oracles     │
│  - Construction of the 4-tier Baseline Ladder (Minimal -> Realistic dbt)   │
│  - Systems Pareto Analysis: Safety Catch Rate vs. Compute/Latency Overhead  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 2: Semantic-SQL-Bench Standalone Decoupled Benchmark Release          │
│  - Decouple Corpus, AST Chaos Operators & DuckDB Fixture Oracles            │
│  - Public Neutral Leaderboard across Frontier & Open Weights Models         │
│  - Standardized Evaluation Harness CLI & Open Source Reference Kit          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔬 Phase 1: The Two-Engine Systems Tradeoff Paper

### 1. Research Question
*What is the Pareto efficiency curve between zero-compute static AST invariant linting and relational execution-backed fixture validation for AI-generated analytical SQL?*

### 2. The 4-Tier Baseline Ladder
To eliminate the strawman baseline problem, the paper evaluates all mutations against a progressive baseline ladder:

| Tier | Evaluation Mechanism | Scope | Example Tests |
| :--- | :--- | :--- | :--- |
| **Tier 0: Syntax Only** | SQL AST Parser | Syntactic validity & engine dialect parsing | `sqlglot.parse_one()` |
| **Tier 1: Minimal Structural** | Standard Schema Linting | Nullity, uniqueness, row bounds | `not_null`, `unique_key`, `row_count_bounds` |
| **Tier 2: Realistic dbt Suite** | Extended Data Quality Tests | Range bounds, categorical sets, foreign keys, non-negative checks | `accepted_values`, `relationships`, `dbt_utils.accepted_range`, singular SQL tests |
| **Tier 3: Static SCOS AST Linter** | Deterministic AST Invariant Compiler | Normalized conjunct matching, grain drop detection (0 ms, 0 warehouse bytes) | `scos_validate_sql` (read-only MCP pre-flight) |
| **Tier 4: Runtime Relational Oracle** | Relational Join Execution | Full empirical counterexample search on data fixtures | `RequiredPopulationAssertion` on DuckDB fixtures |

### 3. Key Empirical Metrics to Report
1. **Mutation Catch Rate ($R_{\text{catch}}$):** Fraction of valid injected semantic defects detected.
2. **False Positive Rate ($\alpha$):** Fraction of compliant/equivalent queries incorrectly flagged.
3. **Execution Latency ($P_{50} / P_{95}$):** Time required to validate candidate query.
4. **Compute Overhead ($USD / \text{Query}$):** Warehouse scanning costs (0 for Tier 3, relational execution for Tier 4).

---

## 🏆 Phase 2: Standalone Semantic-SQL-Bench

### 1. The Core Insight
Instead of selling middleware, define the **standard metric of semantic reliability** that model labs and enterprise buyers use to evaluate Text-to-SQL agents.

### 2. Standalone Package Architecture
```text
semantic-sql-bench/
├── corpus/               # 14 Multi-domain metric contracts (Finance, Healthcare, E-com, Cloud, SaaS)
├── fixtures/             # DuckDB contrastive test fixtures
├── mutations/            # AST Chaos engine (5 operators)
├── oracles/              # Ground-truth execution and assertion engines
├── baseline_ladder/      # Tier 1 (Minimal) and Tier 2 (Realistic dbt) test suites
├── runners/              # Provider adapters (OpenAI, Anthropic, Ollama, vLLM)
└── leaderboard/          # Automated scorecard and dispersion evaluator
```

### 3. Models to Benchmark for Public Release
- **Frontier Commercial:** Claude 3.5 Sonnet, GPT-4o, Gemini 1.5 Pro
- **Open Weights:** Llama-3.1-70B-Instruct, Qwen-2.5-Coder-32B, DeepSeek-Coder-V2
- **Leaderboard Metrics:** Contract Compliance Rate, Appropriate Abstention Rate, Semantic Lift ($\Delta_{\text{sem}}$), Cost-per-Evaluation.
