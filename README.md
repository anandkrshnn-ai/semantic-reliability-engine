# Semantic-SQL-Bench & SCOS Reference Framework

[![CI](https://github.com/anandkrshnn-ai/semantic-reliability-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/anandkrshnn-ai/semantic-reliability-engine/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Specification: SCOS v1.0](https://img.shields.io/badge/spec-SCOS_v1.0-green.svg)](spec/SCOS_V1_SPECIFICATION.md)

**Adversarial Benchmark for Business-Semantic Correctness in Text-to-SQL AI Agents.**

> *An AI-assisted research prototype evaluating business-semantic correctness in AI-generated SQL. Its frozen-corpus mutation results are reproducible against a minimal structural baseline; broader baseline comparisons, live-agent evaluation, production integrations, and security claims remain active research directions.*

---

## 📌 The Problem: The Silent Semantic Failure Gap

Autonomous AI agents generate syntactically valid SQL that executes cleanly on warehouse engines (BigQuery, Snowflake, Databricks, DuckDB), yet **violates core business definitions** (e.g., dropping required active-cohort filters, omitting refund deductions, or miscalculating financial grain).

Standard out-of-the-box structural data quality tests (`not_null`, `unique`, `row_count_bounds`) verify table shapes and nullity, but cannot detect when dynamic SQL logic drops domain arithmetic. **Semantic-SQL-Bench** evaluates agents against explicit, contract-grounded business invariants.

---

## 🏗️ Architecture & Control Plane

```mermaid
flowchart LR
    UserPrompt[User Prompt] --> LLMAgent[AI Agent / Text-to-SQL]
    LLMAgent --> GeneratedSQL[Generated SQL]
    
    subgraph SRE [Semantic Reliability Engine]
        direction TB
        SCOSContract[SCOS Metric Contract] --> ASTCompiler[AST Normalizer]
        GeneratedSQL --> Guardrail[Semantic Invariant Guardrail]
        ASTCompiler --> Guardrail
    end
    
    Guardrail -->|Valid| DataWarehouse[(BigQuery / ClickHouse / DuckDB)]
    Guardrail -->|Drift / Invariant Violation| Feedback[Agent Self-Correction / Retry]
```

### 📐 How SRE Calculates Semantic Drift ($D_{sem}$)
Instead of probabilistic LLM-as-a-judge patterns, SRE uses deterministic **Abstract Syntax Tree (AST) normalization**. The semantic invariant distance between candidate SQL and the metric contract is computed as:

$$D_{sem} = 1 - \frac{\vert{} N_{agent} \cap N_{contract} \vert{}}{\vert{} N_{agent} \cup N_{contract} \vert{}}$$

Where $D_{sem} \in [0, 1]$. Node sets are extracted after AST normalization — formatting, aliases, and commutative predicate ordering are canonicalized away — so $D_{sem} = 0.0$ indicates structural identity with the contract after normalization. The score is reported alongside each decision; blocking itself is driven by the invariant checker and policy engine.

---

## 🚀 Quickstart

### 1. Python SDK (5-Line Guardrail)
```python
from semantic_reliability import SemanticGuardrail

# Load your immutable business metric contract
guard = SemanticGuardrail.from_contract("benchmark_corpus/dev/net_revenue/contract.yaml")

# Evaluate agent-generated SQL prior to execution
result = guard.verify("SELECT SUM(amount) FROM transactions WHERE status = 'active'")

if not result.is_valid:
    print(f"Semantic Drift Detected (Score: {result.drift_score:.2f}):")
    for violation in result.violations:
        print(f" - {violation}")
```

### 2. LangChain & LangGraph SQL Agent Tool Wrapper
Automatically intercepts agent queries and provides self-correction diagnostics to the LLM scratchpad:
```python
from langchain_community.agent_toolkits import create_sql_agent
from semantic_reliability.integrations.langchain import SREGuardrailToolWrapper

# Wrap any database execution tool
guarded_sql_tool = SREGuardrailToolWrapper(
    base_tool=db_tool,
    contract_path="benchmark_corpus/dev/net_revenue/contract.yaml",
    raise_on_drift=False  # Returns feedback directly to agent for self-correction!
)
```

### 3. LiteLLM Proxy Middleware
Enforce zero-code-change semantic guardrailing across your enterprise LLM proxy:
```python
import litellm
from semantic_reliability.integrations.litellm import SRELiteLLMGuardrail

guardrail = SRELiteLLMGuardrail(contract_path="benchmark_corpus/dev/net_revenue/contract.yaml")
litellm.callbacks = [guardrail]
```

---

## 💻 CLI & MCP Server Usage

### Validate a Metric Contract
```bash
sre compile --contract benchmark_corpus/dev/net_revenue/contract.yaml
```

### Launch the Read-Only SCOS MCP Server
```bash
sre mcp-serve --contracts benchmark_corpus/dev --port 8000
```

### Run Live Agent Benchmark & Trajectory Replay
```bash
# Run paired evaluation with an LLM provider (OpenAI, Anthropic, Ollama, or mock scaffolding)
sre benchmark-live --provider mock --rollouts 3 --output benchmark_scorecard.json --trajectories-out runs/trajectories.jsonl

# Zero-compute offline trajectory replay against updated contracts
sre benchmark-replay --trajectories runs/trajectories.jsonl --contracts benchmark_corpus --output replay_scorecard.json
```

---

## 📚 Key Artifacts & Documentation

| Document | Purpose |
| :--- | :--- |
| [**SCOS v1.0 Specification**](spec/SCOS_V1_SPECIFICATION.md) | Formal standard defining semantic invariants, grain, and probes. |
| [**SCOS JSON Schema**](spec/scos-v1.schema.json) | Draft 2020-12 machine-readable contract validation schema. |
| [**Enterprise Architecture & CISO Whitepaper**](docs/ENTERPRISE_ARCHITECTURE_AND_CISO_WHITEPAPER.md) | Technical control plane reference with STRIDE threat matrix and Appendix A empirical results. |
| [**MCP Security & Threat Model**](docs/MCP_SECURITY_AND_THREAT_MODEL.md) | Read-only boundary specifications and signed cryptographic audit checkpoints. |
| [**Benchmark Methodology**](docs/BENCHMARK_METHODOLOGY.md) | Mutation operator taxonomy, validity grading policy, and dual-track protocol. |
| [**Surviving Defect Analysis**](docs/SURVIVING_DEFECT_ANALYSIS.md) | Root-cause post-mortems for surviving mutations, including the v1.1 holdout repairs. |
| [**Release Notes v1.1.0**](docs/RELEASE_NOTES_v1.1.0.md) | Holdout protocol amendment: assertion-registry, adequacy-scorer, and corpus repairs. |
| [**Research Paper (LaTeX)**](paper/main.tex) | Complete academic research paper for peer-reviewed evaluation tracks. |
| [**Launch Manifesto**](docs/SCOS_LAUNCH_MANIFESTO.md) | Public vision for open semantic contract governance in agentic analytics. |

---

## 🧪 Testing & Verification

The test suite contains **144 automated unit tests** covering the AST compiler, mutation operators, reality probes, BigQuery dry-run adapter, MCP JSON-RPC server, signed checkpoints, and trajectory replay:

```bash
pytest tests/ -v
```

---

## 📜 Provenance & AI-Assisted Development Disclosure

This repository was developed with substantial AI-assisted coding in an exploratory session. Human review and independent empirical verification are ongoing. 

- **Verified Core:** The AST mutation engine (`semantic_reliability/testing/mutations`), DuckDB fixture test harness, 14-contract benchmark corpus, and the 144-test unit test suite have been independently executed and verified. Reported holdout results: the v1.0 frozen run (+61.1 pp semantic gain) is reproducible at tag `v1.0.0-phase7`; the v1.1 amended protocol (`v1.1.0-holdout-repair`) — assertion-registry tolerance repair, two documented corpus repairs, and type-aware fixture adequacy — raises the run to **+88.9 pp** (standard 0.0% vs semantic 88.9%, zero `INCONCLUSIVE` models). Both grades are versioned in [holdout_protocol.yaml](benchmark_corpus/holdout/holdout_protocol.yaml); neither supersedes the other silently.
- **Experimental / Scaffolding Modules:** The `gym/` dataset formatting module, live agent loop adapters (`adapters/`), and enterprise governance collateral (CISO whitepaper, cryptographic audit envelope, and FinOps guides) represent research scaffolding and exploratory prototypes. They should not be treated as externally audited enterprise platforms or live model evaluations beyond the exact procedures documented in the repository.

---

## 📄 License

Apache License 2.0. See [LICENSE](LICENSE) for details.
