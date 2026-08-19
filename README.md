# Semantic Reliability Engine (SRE) & SCOS-MCP

[![CI](https://github.com/anandkrshnn-ai/semantic-reliability-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/anandkrshnn-ai/semantic-reliability-engine/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Specification: SCOS v1.0](https://img.shields.io/badge/spec-SCOS_v1.0-green.svg)](spec/SCOS_V1_SPECIFICATION.md)

**Contract-Grounded Evaluation and Runtime Semantic Guardrails for Business Text-to-SQL AI Agents.**

> *AI-generated SQL can be executable and still be semantically wrong. SCOS makes business meaning explicit, testable, and discoverable by agents.*

---

## 📌 The Problem: The Silent Semantic Failure Gap

Autonomous AI agents generate syntactically valid SQL that executes cleanly on warehouse engines (BigQuery, Snowflake, Databricks, DuckDB), yet **violates core business definitions** (e.g., dropping required active-cohort filters, omitting refund deductions, or miscalculating financial grain).

Standard data observability tests evaluate table syntax and row counts; they cannot detect when an agent hallucinates unanchored domain logic.

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

## 📄 License

Apache License 2.0. See [LICENSE](LICENSE) for details.
