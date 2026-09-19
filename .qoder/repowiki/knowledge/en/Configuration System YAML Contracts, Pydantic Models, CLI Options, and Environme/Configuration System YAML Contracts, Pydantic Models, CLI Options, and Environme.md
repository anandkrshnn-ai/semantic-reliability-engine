---
kind: configuration_system
name: 'Configuration System: YAML Contracts, Pydantic Models, CLI Options, and Environment Variables'
category: configuration_system
scope:
    - '**'
source_files:
    - semantic_reliability/compiler/schema.py
    - semantic_reliability/compiler/contracts.py
    - semantic_reliability/firewall/engine.py
    - semantic_reliability/firewall/models.py
    - semantic_reliability/benchmark/protocol.py
    - semantic_reliability/benchmark/llm_client.py
    - semantic_reliability/mcp/server.py
    - semantic_reliability/harness/validity_policy.yaml
    - semantic_reliability/cli.py
    - pyproject.toml
---

## What system/approach is used

The Semantic Reliability Engine (SRE) uses a **multi-layered configuration approach** built around three pillars:

1. **YAML metric contracts** (`contract.yaml`, `semantic_assertions.yaml`, `schema.yml`) — the canonical business definitions of metrics, invariants, probes, and provenance metadata.
2. **Pydantic v2 data models** — strict schema validation for every configuration shape (see `semantic_reliability/compiler/schema.py` for `MetricDefinition`, `SemanticInvariants`, `PopulationInvariant`, `GrainInvariant`, `AggregationInvariant`, `UnitInvariant`, `TimeInvariant`, `MetricProbes`, `ContractProvenance`; see `semantic_reliability/firewall/models.py` for firewall request/response schemas; see `semantic_reliability/benchmark/protocol.py` for `FrozenProtocolConfig`, `BenchmarkScenario`, `AgentTrajectory`, `NetGovernancePolicy`).
3. **Click CLI options + environment variables** — runtime overrides via `--option` flags on the `semantic-reliability` / `sre` entry points, with secrets and provider endpoints read from `os.environ`.

There is no centralized config loader (no `config.py`, no `.env` parser, no `pydantic-settings`). Configuration is loaded **at point-of-use**: YAML files are parsed into Pydantic models directly where they are consumed (e.g. `MetricCompiler.from_yaml_file`, `AssertionSuite.from_yaml_file`, `ContractRegistry._load_contracts`), and environment variables are read inline in the modules that need them.

## Key files and packages

- `semantic_reliability/compiler/schema.py` — defines all contract/metric/probe Pydantic models that validate YAML inputs.
- `semantic_reliability/compiler/contracts.py` — validates candidate SQL against declared semantic invariants (population, grain, aggregation, timezone).
- `semantic_reliability/firewall/engine.py` — `ContractRegistry` auto-discovers `*.yaml` under a directory and registers `MetricDefinition` objects; `SemanticEvaluator` runs policy decisions.
- `semantic_reliability/firewall/models.py` — firewall request/response/enums (`Decision`, `RiskLevel`, `EvaluateRequest`, `EvaluateResponse`).
- `semantic_reliability/benchmark/protocol.py` — `FrozenProtocolConfig` pins protocol version, model id, temperature, max tool calls/iterations, fixture/policy versions to guarantee reproducible benchmark runs.
- `semantic_reliability/benchmark/llm_client.py` — reads `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_BASE_URL` from environment for live LLM calls.
- `semantic_reliability/mcp/server.py` — reads `SRE_AUDIT_SIGNING_KEY` from environment for audit chain signing; otherwise falls back to `secrets.token_hex(32)`.
- `semantic_reliability/harness/validity_policy.yaml` — versioned decision thresholds (`fixture_adequacy_method`, `contract_coverage_method`, conclusive/qualified/inconclusive thresholds).
- `semantic_reliability/cli.py` — Click-based CLI exposing commands (`check`, `mutate`, `benchmark`, `benchmark-corpus`, `evaluate-agent`, `compile`, `probe`, `export-gym`, `audit-gym`, `bq-evaluate`, `dbt-check`, `mcp-serve`, `benchmark-replay`, `benchmark-live`, `audit-provenance`) that accept YAML paths and env-driven provider options.
- `pyproject.toml` — declares package metadata, dependencies (`sqlglot`, `pyyaml`, `pydantic`, `click`, `rich`, `duckdb`, `pandas`, `jsonschema`, `requests`), and entry points `semantic-reliability` / `sre`.

## Architecture and conventions

### Contract-first YAML schema
Every business metric is defined as a YAML file conforming to `MetricDefinition`. The `ContractRegistry` recursively walks a directory (`benchmark_corpus`, user-supplied `--contracts`) loading each `*.yaml`, parsing it through `MetricDefinition(**data)`, and registering it by `metric` key. Unparseable files are skipped with a warning — this makes the registry **tolerant but strict**: valid contracts must match the Pydantic schema exactly.

### Invariant enforcement at parse time
When a contract is loaded, Pydantic validates every field (`metric`, `owner`, `grain`, `sql`, `dialect`, nested `invariants.*`, `probes.*`, `provenance.*`). Invalid YAML fails fast during `MetricCompiler.from_yaml_file` or `ContractRegistry._load_contracts`, so downstream components never receive malformed configs.

### Policy-as-YAML
The `validity_policy.yaml` file centralizes benchmark validity thresholds (`min_fixture_adequacy`, `min_contract_coverage` per conclusive/qualified/inconclusive tiers). It is consumed by `BenchmarkValidityEvaluator` to produce a `validity` and `confidence` badge per model — keeping policy out of Python code.

### Frozen protocol for reproducibility
`FrozenProtocolConfig` pins `protocol_version`, `scenario_commit`, `contract_commit`, `model_id`, `temperature`, `max_tool_calls`, `max_iterations`, `num_rollouts`, `fixture_version`, `policy_version`. This is the single source of truth for what "a benchmark run" means, ensuring replay and live runs are comparable.

### CLI as the primary runtime configuration surface
All user-facing configuration flows through Click options:
- File paths: `--base`, `--candidate`, `--metric`, `--assertions`, `--corpus`, `--manifest`, `--contract`, `--fixture`, `--trajectories`, `--artifacts-dir`, `--output`, `--report`, `--sarif`, `--json-out`, `--dataset`, `--target-dir`, `--audit-citations`.
- Behavior toggles: `--compare/--no-compare`, `--fail-on-drift/--no-fail`, `--fail-on-critical/--no-fail`, `--strict/--no-strict`, `--error-analysis`, `--output-json`, `--output-sarif`.
- Provider/runtime: `--provider`, `--model`, `--api-key`, `--api-base`, `--rollouts`, `--dialect`, `--target-dialect`, `--table-name`, `--fail-on`.
Defaults are baked into the CLI; there is no global config file read at startup.

### Secrets and external endpoints via environment variables
Only secrets and runtime endpoints are configured via environment:
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` — LLM authentication (fallback order in `LiveLLMClient`).
- `OPENAI_BASE_URL` — base URL for OpenAI-compatible endpoints (default `https://api.openai.com/v1`).
- `SRE_AUDIT_SIGNING_KEY` — HMAC signing secret for MCP audit chain checkpoints (auto-generated if absent).
- `GITHUB_TOKEN` — used by `scripts/create_release.py` for GitHub releases.
No `.env` file is loaded; callers must export these before invoking the CLI.

### Audit hash-chain as an integrity mechanism
The MCP server builds a tamper-evident audit log where each event's `event_hash` chains to the previous event's hash starting from a `GENESIS_HASH`. Checkpoints can be signed with `signing_secret` and verified later via `verify_audit_chain()` / `verify_checkpoint()`. This is not "configuration" in the traditional sense but serves as an integrity layer over runtime state.

## Conventions and constraints

- **Contracts are YAML + Pydantic**: Every metric definition lives in a `*.yaml` file and is validated by `MetricDefinition` before use. There is no programmatic way to define a metric without going through this schema.
- **Contract discovery is recursive globbing**: `ContractRegistry(contract_dir)` walks `**/*.yaml` and only registers files containing a top-level `metric` key. Files missing required fields are silently skipped with a warning — consumers should treat this as best-effort loading.
- **CLI options override everything else**: For any given command, Click options take precedence over defaults. There is no layered merge (e.g. no config-file-then-env-then-flag hierarchy); flags are the sole override mechanism.
- **Environment variables are provider-specific**: Only LLM keys, base URLs, and the audit signing key are read from `os.environ`. Application behavior is not controlled via env vars — it is controlled via CLI flags.
- **Version pinning is explicit**: `FrozenProtocolConfig`, `NetGovernancePolicy.version`, `validity_policy.policy_version`, and `SCOS` spec version (`spec/scos-v1.schema.json`) are all explicitly versioned strings. Changes to these require deliberate updates rather than implicit drift.
- **Fail-fast on invalid input**: Pydantic validation errors on YAML → model conversion cause immediate exceptions in `from_yaml_file` / `from_yaml_str`, preventing silent misconfiguration from propagating into evaluation or compilation.
- **Audit logs are append-only and hash-chained**: Once appended, the MCP audit log cannot be modified without breaking the chain; checkpoints provide verifiable snapshots signed by `SRE_AUDIT_SIGNING_KEY`.