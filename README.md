# Semantic Reliability Engine (SRE) & SCOS-MCP

[![CI](https://github.com/anandkrshnn-ai/semantic-reliability-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/anandkrshnn-ai/semantic-reliability-engine/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Specification: SCOS v1.0](https://img.shields.io/badge/spec-SCOS_v1.0-green.svg)](spec/SCOS_V1_SPECIFICATION.md)

**Contract-Grounded Evaluation and Runtime Semantic Guardrails for Business Text-to-SQL AI Agents.**

> *An AI-assisted research prototype for contract-grounded SQL mutation testing and semantic validation. Its frozen-corpus mutation results are reproducible against a minimal structural baseline; broader baseline comparisons, live-agent evaluation, production integrations, licensing, and security claims remain to be completed.*

---

## 📌 The Problem: The Silent Semantic Failure Gap

Autonomous AI agents generate syntactically valid SQL that executes cleanly on warehouse engines (BigQuery, Snowflake, Databricks, DuckDB), yet **violates core business definitions** (e.g., dropping required active-cohort filters, omitting refund deductions, or miscalculating financial grain).

Standard out-of-the-box structural data quality tests (`not_null`, `unique`, `row_count_bounds`) verify table shapes and nullity, but cannot detect when dynamic SQL logic drops domain arithmetic. SCOS defines declarative AST invariant contracts to catch these semantic regressions automatically.

> **Research Prototype Notice:** SCOS detects more injected semantic mutations than the specified minimal structural baseline on the frozen 14-contract corpus. The `gym` and `adapters` packages are experimental research modules.

---

## 🏗️ Architecture Overview

```text
                               ┌────────────────────────┐
                               │   SCOS YAML Contract   │
                               │ (Invariants & Probes)  │
                               └───────────┬────────────┘
                                           │
             ┌─────────────────────────────┼─────────────────────────────┐
             ▼                             ▼                             ▼
   ┌───────────────────┐         ┌───────────────────┐         ┌───────────────────┐
   │ SCOS AST Compiler │         │   Read-Only MCP   │         │ Trajectory Replay │
   │  & Normalization  │         │    Server 2.0     │         │ & Evaluator Gate  │
   └─────────┬─────────┘         └─────────┬─────────┘         └─────────┬─────────┘
             │                             │                             │
             ▼                             ▼                             ▼
   ┌───────────────────┐         ┌───────────────────┐         ┌───────────────────┐
   │  dbt & CI/CD Gate │         │ AI Agent (Claude/ │         │ Tamper-Evident    │
   │ (SARIF Reporting) │         │  GPT-4 / Llama)   │         │ Hash-Chain Audit  │
   └───────────────────┘         └───────────────────┘         └───────────────────┘
```

---

## 🚀 Quickstart

### 1. Installation
```bash
git clone https://github.com/anandkrshnn-ai/semantic-reliability-engine.git
cd semantic-reliability-engine
pip install -e .
```

### 2. Validate a Metric Contract
```bash
sre compile --contract benchmark_corpus/dev/net_revenue/contract.yaml
```

### 3. Launch the Read-Only SCOS MCP Server
```bash
sre mcp-serve --contracts benchmark_corpus/dev --port 8000
```

### 4. Run the Local Demonstration
```bash
python demo/agent.py
```

### 5. Run Live Agent Benchmark & Trajectory Replay
```bash
# Run paired evaluation with an LLM provider (OpenAI, Anthropic, Ollama, or mock scaffolding)
sre benchmark-live --provider mock --rollouts 3 --output benchmark_scorecard.json --trajectories-out runs/trajectories.jsonl

# Or with a real model endpoint:
# sre benchmark-live --provider openai --model gpt-4o --rollouts 3

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
| [**BigQuery & dbt FinOps Guide**](docs/DBT_AND_BIGQUERY_FINOPS_GUIDE.md) | Pre-execution compute cost estimation and CI/CD GitHub Action integration. |
| [**Research Paper (LaTeX)**](paper/main.tex) | Complete academic research paper for peer-reviewed evaluation tracks. |
| [**Launch Manifesto**](docs/SCOS_LAUNCH_MANIFESTO.md) | Public vision for open semantic contract governance in agentic analytics. |

---

## 🧪 Testing & Verification

The test suite contains **112 automated unit tests** covering the AST compiler, mutation operators, reality probes, BigQuery dry-run adapter, MCP JSON-RPC server, signed checkpoints, and trajectory replay:

```bash
pytest tests/ -v
```

---

## 📜 Provenance & AI-Assisted Development Disclosure

This repository was developed with substantial AI-assisted coding in an exploratory session. Human review and independent empirical verification are ongoing. 

- **Verified Core:** The AST mutation engine (`semantic_reliability/mutations`), DuckDB fixture test harness, 14-contract benchmark corpus, and the 112-test unit test suite have been independently executed and verified. The reported holdout mutation catch rate (+61.1 pp) reflects code-path reproducibility against the specified minimal structural baseline (`not_null`, `unique_key`, `row_count_bounds`).
- **Experimental / Scaffolding Modules:** The `gym/` dataset formatting module, live agent loop adapters (`adapters/`), and enterprise governance collateral (CISO whitepaper, cryptographic audit envelope, and FinOps guides) represent research scaffolding and exploratory prototypes. They should not be treated as externally audited enterprise platforms or live model evaluations beyond the exact procedures documented in the repository.

---

## 📄 License

Apache License 2.0. See [LICENSE](LICENSE) for details.
