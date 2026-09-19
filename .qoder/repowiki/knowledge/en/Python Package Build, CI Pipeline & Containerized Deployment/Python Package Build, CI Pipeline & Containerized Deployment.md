---
kind: build_system
name: Python Package Build, CI Pipeline & Containerized Deployment
category: build_system
scope:
    - '**'
source_files:
    - pyproject.toml
    - requirements.txt
    - .github/workflows/ci.yml
    - .github/workflows/sre-dbt-semantic-gate.yml
    - demo/Dockerfile
    - demo/docker-compose.yml
    - deploy/k8s/semantic_firewall_sidecar.yaml
    - scripts/create_release.py
---

## Build System Overview

The Semantic Reliability Engine is a Python monorepo built with **setuptools** (PEP 517 backend) and distributed as the `semantic-reliability-engine` package on PyPI. There are no Makefiles or shell-based build scripts — all build, test, packaging, and deployment logic lives in `pyproject.toml`, GitHub Actions workflows, Dockerfiles, and a small set of helper scripts.

## Packaging & Distribution

- **Build backend**: `setuptools.build_meta` with `setuptools>=61.0` declared in `[build-system]`.
- **Package metadata**: `name = semantic-reliability-engine`, `version = 0.1.0`, `requires-python >= 3.10`, Apache-2.0 license.
- **Runtime dependencies** pinned by minimum version: `sqlglot>=25.0.0`, `pyyaml>=6.0.1`, `pydantic>=2.0.0`, `click>=8.1.0`, `rich>=13.0.0`, `duckdb>=1.0.0`, `pandas>=2.0.0`, `jsonschema>=4.0.0`, `requests>=2.31.0`.
- **Optional dev dependency**: `pytest>=8.0.0` under `[project.optional-dependencies] dev`.
- **Entry points**: two CLI commands registered via `[project.scripts]` — `semantic-reliability` and `sre`, both pointing to `semantic_reliability.cli:main`.
- **Package discovery**: `tool.setuptools.packages.find` includes only `semantic_reliability*` from the repo root.
- **Legacy lockfile**: `requirements.txt` mirrors the runtime deps plus pytest; it is installed alongside the editable install in CI but is not used as the canonical source of truth (that role belongs to `pyproject.toml`).

## Test & Lint Configuration

- **Pytest** configured in `[tool.pytest.ini_options]`: tests live under `tests/`, files matching `test_*.py`, with `.` added to `pythonpath` so imports resolve against the repo root.
- The CI workflow runs `pytest tests/ -v` as the primary gate.

## CI Pipelines (GitHub Actions)

Two workflows under `.github/workflows/`:

1. **`ci.yml` — "CI & Benchmark Integrity"**
   - Triggers on push/PR to `main` and `master`.
   - Uses `ubuntu-latest` + Python 3.11 with pip cache enabled.
   - Installs the package editably (`pip install -e .`) plus `requirements.txt`.
   - Runs the full test suite: `pytest tests/ -v`.
   - Executes provenance/citation audits against `examples/assertions` and `benchmark_corpus` via the `audit-provenance` CLI subcommand.
   - Runs the dual-track benchmark suite: `benchmark-corpus --split all --error-analysis --json-out ci_benchmark_results.json` and uploads `ci_benchmark_results.json` as an artifact.

2. **`sre-dbt-semantic-gate.yml` — "SRE Semantic Gate"**
   - Triggered on PRs that touch `models/**/*.sql`, `contracts/**/*.yaml`, or `dbt_project.yml`.
   - Requires `GITHUB_TOKEN` for SARIF upload and `DBT_PROFILES_YML` / `GOOGLE_APPLICATION_CREDENTIALS` secrets.
   - Installs `dbt-bigquery` and publishes `semantic-reliability-engine` from PyPI (not the local checkout), then compiles the dbt manifest.
   - Computes changed SQL models vs `origin/main` and runs `sre dbt-check` per model against its contract, failing on `critical` severity and emitting per-model SARIF artifacts.
   - Uploads all SARIF files to GitHub Code Scanning under category `semantic-reliability`.

## Containerization & Runtime Deployment

- **Demo container** (`demo/Dockerfile`): based on `python:3.11-slim`, installs runtime deps directly via pip, copies the repo with non-root ownership (`appuser:appgroup` uid/gid 10001), installs the package in editable mode (`pip install -e .`), exposes port 8000, defines a healthcheck probing TCP 8000, and defaults to running `demo/agent.py`.
- **Docker Compose** (`demo/docker-compose.yml`): defines two services on a bridge network `sre_demo_net` — `scos-mcp-server` (runs `sre mcp-serve --contracts benchmark_corpus/dev --port 8000`) and `analytics-agent-demo` (runs `demo/agent.py`), both with `no-new-privileges:true`, `cap_drop: ALL`, CPU/memory limits, and `PYTHONUNBUFFERED=1`.
- **Kubernetes sidecar** (`deploy/k8s/semantic_firewall_sidecar.yaml`): a Deployment named `analytics-agent-with-firewall` in namespace `analytics` with two containers — a `text2sql-agent` image and the SRE firewall sidecar `ghcr.io/anandkrshnn-ai/semantic-reliability-engine:v1.0.0` running `uvicorn semantic_reliability.firewall.main:app` on port 8080. Contracts are mounted read-only from a ConfigMap `sre-metric-contracts`. Health probes hit `/health`; Prometheus scraping is annotated at `/metrics:8080`.

## Release Process

- **Versioning**: single static version `0.1.0` in `pyproject.toml`; release notes live under `docs/RELEASE_NOTES_v*.md`.
- **Publishing script**: `scripts/create_release.py` calls the GitHub Releases REST API to create a prerelease tag (currently hardcoded to `v1.0.0-phase7`) using a `GITHUB_TOKEN` env var or CLI argument. It reads release notes from the corresponding `docs/RELEASE_NOTES_*` file. No automated PyPI publish step was found in this repository.
- A companion `scripts/update_release.py` exists (referenced by the directory listing) but was not inspected here.

## Conventions Observed

- All Python tooling targets **Python 3.11** in CI and containers, despite the package declaring `>=3.10`.
- Dependencies are declared once in `pyproject.toml`; `requirements.txt` is kept in sync but treated as a secondary convenience file.
- Tests are always run against an **editable install** (`pip install -e .`) so they exercise the checked-out code rather than a published wheel.
- The demo container follows security best practices: non-root user, dropped capabilities, resource limits, and a TCP healthcheck.
- The Kubernetes sidecar pattern mounts contracts as a read-only ConfigMap volume and configures liveness/readiness probes on `/health`.
- CI gates PRs touching SQL/contract files through a separate workflow that runs dbt compilation and per-model semantic checks, producing SARIF results for GitHub Advanced Security.